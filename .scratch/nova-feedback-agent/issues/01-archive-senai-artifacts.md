# 01 — Archive SENAI-specific artifacts and clean up runtime

**What to build:** Move SENAI-specific source documents, syllabus files, and scrapers into a clean `archive/senai/` directory. Remove the live seat count refresher and availability scraping from the runtime lifecycle, simplifying the app to focus strictly on interactive feedback and support.

**Blocked by:** None — can start immediately.

**Status:** resolved

- [x] Move `Apostila_IA_Generativa_Capitulos_1_e_2_v0.4.docx` and `Plano_Mestre_Curso_IA_Generativa_v2.0.docx` to `archive/senai/`.
- [x] Move `content/apostila.pdf` and `content/enrollment_card.yaml` to `archive/senai/`.
- [x] Move `bella/availability.py` and `bella/seat_count.py` to `archive/senai/`.
- [x] Remove `SeatCountRefresher` and seat-count background tasks from `bella/app.py` and `bella/composition.py`.
- [x] Ensure existing unit tests run and pass without the retired SENAI components.

## Implementation Notes

- Created `archive/senai/` and `archive/senai/tests/`.
- Moved SENAI course documentation (`Apostila_IA_Generativa_Capitulos_1_e_2_v0.4.docx`, `Plano_Mestre_Curso_IA_Generativa_v2.0.docx`), content assets (`content/apostila.pdf`, `content/enrollment_card.yaml`), and scraper modules (`bella/availability.py`, `bella/seat_count.py`, `bella/scripts/check_seat_count.py`) to `archive/senai/`.
- Moved retired unit test suites (`tests/test_seat_count.py`, `tests/test_senai_availability.py`) to `archive/senai/tests/`.
- Cleaned up runtime and app lifecycle:
  - `bella/app.py`: Removed `SeatCountRefresher` import, `seat_count_refresher` parameter from `create_app`, and the refresher background task/teardown in `lifespan`.
  - `bella/composition.py`: Removed `SenaiAvailabilitySource`, `SeatCountHolder`, `SeatCountRefresher`, and simplified `Runtime` and `build_runtime` to only manage the pipeline.
  - `bella/course_content.py`: Removed `SeatCountHolder` and `DEFAULT_MAX_AGE_SECONDS` imports and references, simplifying `render_enrollment_card()`.
  - `bella/config.py`: Removed `DEFAULT_MAX_AGE_SECONDS` import, added archive fallback paths for `DEFAULT_ENROLLMENT_CARD_PATH` and `DEFAULT_APOSTILA_PATH`.
  - `tests/conftest.py`: Removed `SeatCountRefresher` import and parameter from `make_test_client`.
  - `pyproject.toml` and `.gitignore`: Added `--basetemp=.pytest_tmp` configuration for robust test runs in Windows environments.
- Validation:
  - `pytest`: 200 passed, 7 skipped, 0 failures.
  - `mypy`: 0 errors across all 42 source files.
