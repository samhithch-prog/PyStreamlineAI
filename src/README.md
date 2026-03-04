# Source Layout

This project is moving from a single-file app toward a layered structure:

- `src/controller/`: page/app flow orchestration (`main`-level routing).
- `src/dto/`: data-transfer contracts between layers.
- `src/repository/`: DB-focused data access.
- `src/service/`: business rules and use-case logic.
- `src/ui/`: visual layer helpers (style rendering, UI-specific helpers).

Current migration implemented:

- Thin runner entrypoint in `app.py` (`AppRunner`) that calls `src/app_runtime.py`.
- App startup and root routing in `src/controller/app_controller.py`.
- Runtime/auth DTOs in `src/dto/runtime_dto.py` and `src/dto/auth_dto.py`.
- Auth persistence operations in `src/repository/auth_repository.py`.
- Auth use-cases in `src/service/auth_service.py`.
- Shared auth UI helper in `src/ui/auth_view.py`.
- Large UI style renderer in `src/ui/styles.py`.

Guideline for future changes:

1. Add or update DTOs first when introducing new cross-layer data.
2. Keep orchestration in `controller` (what runs, and in which order).
3. Keep rendering/styling in `ui`.
4. Keep persistence/business logic in dedicated `repository`/`service` modules.
