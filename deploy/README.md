# deploy/

Эта директория содержит только серверную инфраструктуру CI/CD.

## deploy/state/

Runtime-артефакты процесса деплоя (`.deploy-commit`, `.deploy-state`,
`.deploy-last-success` и т.д.), создаются и обновляются исключительно
скриптом `/usr/local/bin/fastlink-ci` на production-сервере.

- Никогда не коммитятся в git (см. `.gitignore`: `deploy/state/`).
- Не используются и не создаются при локальной разработке.
- Их назначение — детерминированный rollback и диагностика последнего
  успешного/неудачного деплоя. Подробности — см. `.github/workflows/deploy.yml`.
