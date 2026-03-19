import json
import logging
import os
import re
from hashlib import sha256
from time import monotonic
from typing import Any

from openai import AsyncOpenAI, BadRequestError, InternalServerError
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.services.ai_gateway import AIGateway

logger = logging.getLogger(__name__)
settings = get_settings()


SYSTEM_PROMPT = (
    "You are ZoSwi's live senior technical interviewer for software engineering roles. "
    "Sound natural, professional, and human-like. Keep each question concise, ask only one question at a time, "
    "and adapt follow-up questions based on the candidate's last answer. "
    "If the answer is vague, ask a clarifying follow-up before changing topics. "
    "Use a short, natural acknowledgment before follow-up questions to feel conversational, without fixed templates. "
    "Internally evaluate technical depth, communication clarity, and confidence while keeping the interview conversational."
)


class AIService:
    def __init__(self) -> None:
        self._clients_by_key: dict[str, AsyncOpenAI] = {}
        self._cached_db_key: str | None = None
        self._cached_db_key_at: float = 0.0
        self._db_lookup_error_logged = False
        self.gateway = AIGateway(self._get_client)

    async def transcribe_audio_bytes(
        self,
        audio_bytes: bytes,
        mime_type: str = "audio/webm",
        db: AsyncSession | None = None,
    ) -> str:
        client = await self._get_client(db)
        if not client:
            logger.warning("ZoSwi AI key is missing. Using fallback transcription.")
            return "Transcription unavailable because ZoSwi API AI key is not configured."

        suffix, upload_mime = self._resolve_audio_upload_format(mime_type)

        models = self._stt_model_chain()
        if not models:
            return "Audio transcription model is not configured."

        for index, model_name in enumerate(models):
            file_payload = (f"candidate_chunk.{suffix}", audio_bytes, upload_mime)
            is_last_model = index == len(models) - 1

            try:
                response = await self.gateway.transcribe(
                    model=model_name,
                    file_payload=file_payload,
                    fallback_models=[],
                    db=db,
                )
                transcript = getattr(response, "text", "").strip()
                if index > 0:
                    logger.info(
                        "Recovered transcription via fallback model '%s' (primary '%s').",
                        model_name,
                        models[0],
                    )
                return transcript or "No transcript detected."
            except InternalServerError as exc:
                if not is_last_model:
                    logger.warning(
                        "STT model '%s' failed with upstream 500. Retrying with fallback model '%s'.",
                        model_name,
                        models[index + 1],
                    )
                    continue
                logger.warning(
                    "STT upstream failed after all models (mime=%s upload_mime=%s bytes=%s): %s",
                    mime_type,
                    upload_mime,
                    len(audio_bytes),
                    exc,
                )
                return "Audio transcription service is temporarily unavailable."
            except BadRequestError as exc:
                if upload_mime == "audio/webm":
                    retry_mime = "audio/webm;codecs=opus"
                    retry_payload = (f"candidate_chunk.{suffix}", audio_bytes, retry_mime)
                    try:
                        logger.warning(
                            "Retrying STT decode with codec-specific mime (model=%s mime=%s bytes=%s).",
                            model_name,
                            retry_mime,
                            len(audio_bytes),
                        )
                        response = await self.gateway.transcribe(
                            model=model_name,
                            file_payload=retry_payload,
                            fallback_models=[],
                            db=db,
                        )
                        transcript = getattr(response, "text", "").strip()
                        return transcript or "No transcript detected."
                    except BadRequestError:
                        pass
                    except Exception as retry_exc:
                        if not is_last_model:
                            logger.warning(
                                "STT model '%s' failed on codec-specific retry (%s). Retrying fallback model '%s'.",
                                model_name,
                                type(retry_exc).__name__,
                                models[index + 1],
                            )
                            continue
                        logger.warning(
                            "Codec-specific retry failed (mime=%s bytes=%s): %s",
                            retry_mime,
                            len(audio_bytes),
                            retry_exc,
                        )
                        return "Audio could not be decoded for this turn."

                if not is_last_model:
                    logger.warning(
                        "STT model '%s' rejected audio. Retrying with fallback model '%s'.",
                        model_name,
                        models[index + 1],
                    )
                    continue
                logger.warning(
                    "Transcription rejected (mime=%s upload_mime=%s bytes=%s): %s",
                    mime_type,
                    upload_mime,
                    len(audio_bytes),
                    exc,
                )
                return "Audio could not be decoded for this turn."
            except Exception as exc:
                if not is_last_model:
                    logger.warning(
                        "STT model '%s' failed (%s). Retrying with fallback model '%s'.",
                        model_name,
                        type(exc).__name__,
                        models[index + 1],
                    )
                    continue
                logger.exception(
                    "Transcription request failed (mime=%s upload_mime=%s bytes=%s)",
                    mime_type,
                    upload_mime,
                    len(audio_bytes),
                )
                return "Audio transcription failed for this turn."

        return "Audio transcription failed for this turn."

    async def generate_opening_question(
        self,
        role: str,
        db: AsyncSession | None = None,
        session_seed: str | None = None,
        interview_type: str = "mixed",
    ) -> str:
        normalized_type = self._normalize_interview_type(interview_type)
        base_question = self._build_seeded_opening_question(
            role=role,
            session_seed=session_seed,
            interview_type=normalized_type,
        )
        client = await self._get_client(db)
        if not client:
            return base_question

        rotated_topics = self._rotate_by_seed(
            self._role_topics(role, normalized_type),
            f"{session_seed or role}:{normalized_type}:opening",
        )
        candidate_topics = rotated_topics[:4]
        session_hint = session_seed or role
        focus_guidance = self._interview_type_guidance(normalized_type)

        try:
            response = await self.gateway.chat_completion(
                model=settings.llm_model,
                fallback_models=[item for item in str(settings.llm_fallback_models or "").split(",") if item.strip()],
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": (
                            f"Role: {role}\n"
                            f"Interview Type: {normalized_type}\n"
                            f"Focus Guidance: {focus_guidance}\n"
                            f"Session Seed: {session_hint}\n"
                            f"Topic Candidates: {candidate_topics}\n"
                            f"Base Opening Question: {base_question}\n"
                            "Rewrite the base question for this specific session.\n"
                            "Rules:\n"
                            "- Start with a short human acknowledgment (2-6 words).\n"
                            "- Ask exactly one question aligned to Interview Type.\n"
                            "- Keep it under 30 words.\n"
                            "- Do not use the same opening style as a generic intro every time.\n"
                            "- Do not use repeated canned acknowledgment phrases.\n"
                            "- Keep the intent close to Base Opening Question."
                        ),
                    },
                ],
                temperature=0.7,
                db=db,
            )
            question = self._clean_question(response.choices[0].message.content or "")
        except Exception as exc:
            logger.warning("Opening question generation failed; using fallback question: %s", exc)
            return base_question

        if not question:
            return base_question
        return self._ensure_active_question(
            question,
            candidate_answer="",
            previous_ai_questions=[],
            role=role,
            interview_type=normalized_type,
        )

    async def generate_next_question_and_evaluation(
        self,
        role: str,
        current_question: str,
        candidate_answer: str,
        transcript_history: list[dict[str, str]],
        db: AsyncSession | None = None,
        interview_type: str = "mixed",
    ) -> dict[str, Any]:
        normalized_type = self._normalize_interview_type(interview_type)
        client = await self._get_client(db)
        if not client:
            return self._fallback_turn(candidate_answer, role, transcript_history, normalized_type)

        previous_ai_questions = [
            str(item.get("text", "")).strip()
            for item in transcript_history
            if str(item.get("speaker", "")).strip() == "ai" and str(item.get("text", "")).strip()
        ]

        prompt = (
            "Evaluate the candidate's latest answer and propose the next question.\n"
            "Return JSON only with keys:\n"
            "technical_accuracy, communication_clarity, confidence, overall_rating, summary_text, next_question.\n"
            "Scores must be floats from 0 to 10.\n"
            f"Role: {role}\n"
            f"Interview Type: {normalized_type}\n"
            f"Focus Guidance: {self._interview_type_guidance(normalized_type)}\n"
            f"Current Question: {current_question}\n"
            f"Candidate Answer: {candidate_answer}\n"
            f"Recent Transcript History: {transcript_history[-8:]}\n"
            f"Previous AI Questions: {previous_ai_questions[-8:]}\n"
            "Rules for next_question:\n"
            "- Start with a short human acknowledgement tailored to the candidate's answer.\n"
            "- Ask exactly one new question aligned to Interview Type.\n"
            "- Do not repeat or paraphrase any previous AI question too closely.\n"
            "- Avoid fixed canned phrase templates.\n"
            "- If the latest answer is vague, ask one clarifying follow-up on the same topic."
        )

        try:
            response = await self.gateway.chat_completion(
                model=settings.llm_model,
                fallback_models=[item for item in str(settings.llm_fallback_models or "").split(",") if item.strip()],
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.55,
                db=db,
            )
            payload = json.loads(response.choices[0].message.content or "{}")
            normalized = self._normalize_turn(payload)
            normalized["next_question"] = self._ensure_active_question(
                normalized["next_question"],
                candidate_answer=candidate_answer,
                previous_ai_questions=previous_ai_questions,
                role=role,
                interview_type=normalized_type,
            )
            return normalized
        except Exception as exc:
            logger.warning("Turn generation failed; using fallback scoring/question: %s", exc)
            return self._fallback_turn(candidate_answer, role, transcript_history, normalized_type)

    async def synthesize_speech(self, text: str, db: AsyncSession | None = None) -> bytes:
        if not text.strip():
            return b""

        try:
            return await self.gateway.synthesize_speech(
                model=settings.tts_model,
                voice=settings.tts_voice,
                text_input=text,
                db=db,
            )
        except Exception as exc:
            logger.warning("TTS generation failed; continuing without AI audio: %s", exc)
            return b""

    async def _get_client(self, db: AsyncSession | None) -> AsyncOpenAI | None:
        api_key = await self._resolve_api_key(db)
        if not api_key:
            return None

        cached = self._clients_by_key.get(api_key)
        if cached:
            return cached

        created = AsyncOpenAI(api_key=api_key)
        self._clients_by_key[api_key] = created
        return created

    async def _resolve_api_key(self, db: AsyncSession | None) -> str:
        key_from_db = await self._read_key_from_db(db)
        if key_from_db:
            return key_from_db

        env_key = str(settings.openai_api_key or "").strip()
        if env_key:
            return env_key

        return str(os.getenv("ZOSWI_AI_API_KEY", "")).strip()

    async def _read_key_from_db(self, db: AsyncSession | None) -> str:
        if db is None:
            return ""

        now = monotonic()
        ttl = max(1, int(settings.db_api_key_cache_ttl_seconds))
        if self._cached_db_key is not None and (now - self._cached_db_key_at) < ttl:
            return self._cached_db_key

        try:
            primary_key = settings.openai_api_setting_key
            legacy_spaced_key = primary_key.replace("_", " ")
            fallback_openai_key = "OPENAI_API_KEY"
            # Isolate app_settings lookup failures from the caller transaction.
            # Without this savepoint, a missing table/permission error can poison
            # the outer interview transaction and trigger "current transaction is aborted".
            async with db.begin_nested():
                result = await db.execute(
                    text(
                        """
                        SELECT setting_value
                        FROM app_settings
                        WHERE setting_key IN (:primary_key, :legacy_spaced_key, :fallback_openai_key)
                        ORDER BY CASE
                          WHEN setting_key = :primary_key THEN 0
                          WHEN setting_key = :legacy_spaced_key THEN 1
                          ELSE 2
                        END
                        LIMIT 1
                        """
                    ),
                    {
                        "primary_key": primary_key,
                        "legacy_spaced_key": legacy_spaced_key,
                        "fallback_openai_key": fallback_openai_key,
                    },
                )
            value = str(result.scalar_one_or_none() or "").strip()
            self._cached_db_key = value
            self._cached_db_key_at = now
            return value
        except Exception as exc:
            if not self._db_lookup_error_logged:
                logger.info("Unable to read API key from app_settings (%s): %s", settings.openai_api_setting_key, exc)
                self._db_lookup_error_logged = True
            self._cached_db_key = ""
            self._cached_db_key_at = now
            return ""

    def _normalize_turn(self, payload: dict[str, Any]) -> dict[str, Any]:
        technical = self._clamp(payload.get("technical_accuracy", 0.0))
        clarity = self._clamp(payload.get("communication_clarity", 0.0))
        confidence = self._clamp(payload.get("confidence", 0.0))
        overall = self._clamp(payload.get("overall_rating", (technical + clarity + confidence) / 3))
        summary_text = str(payload.get("summary_text", "No summary provided.")).strip() or "No summary provided."
        next_question = str(payload.get("next_question", "")).strip() or (
            "Tell me about a production issue you handled and your debugging process."
        )
        return {
            "technical_accuracy": technical,
            "communication_clarity": clarity,
            "confidence": confidence,
            "overall_rating": overall,
            "summary_text": summary_text,
            "next_question": next_question,
        }

    def _fallback_turn(
        self,
        candidate_answer: str,
        role: str,
        transcript_history: list[dict[str, str]] | None = None,
        interview_type: str = "mixed",
    ) -> dict[str, Any]:
        words = len(candidate_answer.split())
        base = 5.0 if words < 30 else 6.5 if words < 80 else 7.5
        normalized_type = self._normalize_interview_type(interview_type)
        previous_ai_questions = [
            str(item.get("text", "")).strip()
            for item in (transcript_history or [])
            if str(item.get("speaker", "")).strip() == "ai" and str(item.get("text", "")).strip()
        ]
        return {
            "technical_accuracy": base,
            "communication_clarity": min(base + 0.4, 10.0),
            "confidence": base,
            "overall_rating": min(base + 0.2, 10.0),
            "summary_text": "Fallback scoring used because ZoSwi AI API key is not configured.",
            "next_question": self._build_fallback_follow_up(
                role,
                candidate_answer,
                previous_ai_questions,
                normalized_type,
            ),
        }

    @staticmethod
    def _clamp(value: Any) -> float:
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            numeric = 0.0
        return max(0.0, min(10.0, round(numeric, 2)))

    def _ensure_active_question(
        self,
        question: str,
        candidate_answer: str,
        previous_ai_questions: list[str],
        role: str,
        interview_type: str = "mixed",
    ) -> str:
        normalized_type = self._normalize_interview_type(interview_type)
        cleaned = self._clean_question(question)
        if not cleaned:
            return self._build_fallback_follow_up(role, candidate_answer, previous_ai_questions, normalized_type)

        normalized = self._normalize_text(cleaned)
        for previous in previous_ai_questions[-8:]:
            if self._normalize_text(previous) == normalized:
                return self._build_fallback_follow_up(
                    role,
                    candidate_answer,
                    previous_ai_questions,
                    normalized_type,
                )

        if "?" not in cleaned:
            cleaned = cleaned.rstrip(".") + "?"
        return cleaned

    def _build_seeded_opening_question(
        self,
        role: str,
        session_seed: str | None,
        interview_type: str = "mixed",
    ) -> str:
        normalized_type = self._normalize_interview_type(interview_type)
        topics = self._rotate_by_seed(self._role_topics(role, normalized_type), f"{session_seed or role}:{normalized_type}:topic")
        topic = topics[0] if topics else "a technical project you shipped recently"
        return f"For this {role} role, can you walk me through {topic}?"

    def _build_fallback_follow_up(
        self,
        role: str,
        candidate_answer: str,
        previous_ai_questions: list[str],
        interview_type: str = "mixed",
    ) -> str:
        normalized_type = self._normalize_interview_type(interview_type)
        topics = self._role_topics(role, normalized_type)
        used_text = self._normalize_text(" ".join(previous_ai_questions))
        selected_topic = topics[0] if topics else "a real system design decision you made"
        for topic in topics:
            topic_marker = self._normalize_text(topic).split(" ")[0]
            if topic_marker and topic_marker not in used_text:
                selected_topic = topic
                break
        return f"For this {role} role, can you walk me through {selected_topic}?"

    def _clean_question(self, text: str) -> str:
        cleaned = str(text or "").strip()
        cleaned = re.sub(r"\s+", " ", cleaned)
        return cleaned.strip()

    def _normalize_text(self, text: str) -> str:
        normalized = re.sub(r"[^a-z0-9\s]", " ", str(text or "").lower())
        return re.sub(r"\s+", " ", normalized).strip()

    def _role_topics(self, role: str, interview_type: str = "mixed") -> list[str]:
        normalized_type = self._normalize_interview_type(interview_type)
        behavioral_topics = [
            "a time you disagreed with a teammate and how you resolved it",
            "a high-pressure delivery situation and how you managed priorities",
            "a project failure and what you changed afterward",
            "a time you influenced decisions without formal authority",
        ]
        if normalized_type == "behavioral":
            return behavioral_topics

        role_lower = role.lower()
        technical_topics: list[str]
        if "backend" in role_lower:
            technical_topics = [
                "a distributed API design decision and trade-offs",
                "how you tuned database query performance under load",
                "a production outage you debugged end-to-end",
                "how you designed idempotent and reliable background jobs",
            ]
        elif "frontend" in role_lower:
            technical_topics = [
                "how you improved rendering performance for a complex UI",
                "state management trade-offs in a large React app",
                "how you built resilient async data flows in the browser",
                "a difficult accessibility issue you solved",
            ]
        elif "data" in role_lower or "ml" in role_lower:
            technical_topics = [
                "a data pipeline reliability challenge you solved",
                "how you handled model performance regression in production",
                "trade-offs you made in feature engineering",
                "how you designed validation and monitoring for data quality",
            ]
        else:
            technical_topics = [
                "a system design decision you made and the trade-offs",
                "how you debugged a high-impact production issue",
                "how you improved performance in a real application",
                "a case where you balanced speed and code quality",
                "how you designed for reliability under scale",
            ]

        if normalized_type == "technical":
            return technical_topics
        return technical_topics + behavioral_topics

    @staticmethod
    def _normalize_interview_type(interview_type: str) -> str:
        cleaned = str(interview_type or "").strip().lower().replace(" ", "_").replace("-", "_")
        if cleaned in {"technical", "behavioral"}:
            return cleaned
        if cleaned == "behavioural":
            return "behavioral"
        return "mixed"

    @staticmethod
    def _interview_type_guidance(interview_type: str) -> str:
        if interview_type == "technical":
            return "Prioritize implementation depth, debugging, architecture, performance, and trade-offs."
        if interview_type == "behavioral":
            return "Prioritize real past examples, ownership, collaboration, communication, and decision-making."
        return "Mix technical depth with behavioral signal checks while staying role-relevant."

    def _rotate_by_seed(self, values: list[str], seed: str) -> list[str]:
        if not values:
            return values
        digest = sha256(seed.encode("utf-8")).hexdigest()
        index = int(digest[:8], 16) % len(values)
        return values[index:] + values[:index]

    def _stt_model_chain(self) -> list[str]:
        primary = str(settings.stt_model or "").strip()
        fallback_raw = str(settings.stt_fallback_models or "").strip()
        fallback_models = [item.strip() for item in fallback_raw.split(",") if item.strip()]

        chain: list[str] = []
        if primary:
            chain.append(primary)
        for model in fallback_models:
            if model not in chain:
                chain.append(model)
        return chain

    def _resolve_audio_upload_format(self, mime_type: str) -> tuple[str, str]:
        raw = str(mime_type or "").strip().lower()
        base_mime = raw.split(";", 1)[0].strip()

        if "mp4" in base_mime:
            return "mp4", "audio/mp4"
        if "wav" in base_mime:
            return "wav", "audio/wav"
        if "ogg" in base_mime:
            return "ogg", "audio/ogg"
        if "mpeg" in base_mime or "mp3" in base_mime:
            return "mp3", "audio/mpeg"
        if "webm" in base_mime:
            return "webm", "audio/webm"
        return "webm", "audio/webm"
