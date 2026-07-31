# Production Readiness Review v1.0
## Финальная проверка готовности к PHASE-04.3

**Дата:** 2026-07-29
**Версия:** 1.0
**Статус:** Утверждён
**Основание:** Architecture v1.0.1

---

## Содержание

1. Проверка плана реализации
2. Анализ точек интеграции
3. Legacy Exit Plan
4. Контроль обратной совместимости
5. Dependency Injection Review
6. Production Safety Checklist
7. План тестирования
8. Production Rollback Plan
9. Performance Review
10. Code Quality Rules
11. ARCHITECTURE FREEZE CONFIRMATION
12. FINAL GO / NO GO

---

## 1. Проверка плана реализации

### 1.1 Предлагаемый порядок

```
Step 01: UriValueSerializer
  deps:   ∅
  выход:  корректная сериализация значений (json.dumps вместо str)

Step 02: TransportConfig
  deps:   UriValueSerializer
  выход:  иерархия типизированных конфигов

Step 03: TransportSerializer
  deps:   TransportConfig
  выход:  сериализаторы для xHTTP, WS, gRPC (первые 3)

Step 04: TransportRegistry
  deps:   TransportSerializer
  выход:  registry с первыми 3 сериализаторами

Step 05: CapabilityModel
  deps:   ∅
  выход:  тип данных для capability

Step 06: CapabilityRegistry
  deps:   CapabilityModel
  выход:  registry с профилями V2RayNG, sing-box, Hiddify

Step 07: ExporterRegistry
  deps:   UriExporter (создать до registry или зарегистрировать после)
  выход:  registry с uri, json, yaml

Step 08: UriExporter
  deps:   TransportRegistry, CapabilityModel
  выход:  единый URI-экспортёр

Step 09: SubscriptionBuilder
  deps:   ExporterRegistry, CapabilityRegistry
  выход:  сборщик subscription-ответов

Step 10: Integration
  deps:   SubscriptionBuilder
  выход:  subscription_server.py использует новую архитектуру

Step 11: Replace build_uri()
  deps:   UriExporter
  выход:  старый _build_vless_uri() больше не вызывается

Step 12: Remove legacy
  deps:   Step 10, Step 11
  выход:  legacy-код удалён
```

### 1.2 Зависимости (граф)

```
UriValueSerializer ──────────────────────────────────┐
    └──► TransportConfig                              │
           └──► TransportSerializer                   │
                  └──► TransportRegistry              │
                         └──► UriExporter ◄───────────┘
                                └──► ExporterRegistry
CapabilityModel ───► CapabilityRegistry ──┐
    └──► UriExporter ◄────────────────────┘
         └──► ExporterRegistry ──► SubscriptionBuilder
                                       └──► Integration
                                              └──► Replace build_uri
                                                     └──► Remove legacy
```

### 1.3 Анализ порядка

**Достоинства:**
- UriValueSerializer первым — фикс BUG-001 изолированно
- CapabilityModel и TransportConfig независимы → параллельная разработка
- UriExporter собирается предпоследним, когда все зависимости готовы

**Риски:**
- Step 04 (TransportRegistry) без Step 08 (UriExporter) не имеет потребителя — промежуточный артефакт не верифицируется
- Step 07 (ExporterRegistry) регистрирует UriExporter, который создаётся в Step 08 — это циклическая зависимость по времени создания

**Рекомендуемый скорректированный порядок:**

```
Шаг 1: UriValueSerializer          (без изменений)
Шаг 2: TransportConfig             (без изменений)
Шаг 3: CapabilityModel             (параллельно с TransportConfig)
Шаг 4: TransportSerializer         (зависит от TransportConfig)
Шаг 5: CapabilityRegistry          (зависит от CapabilityModel)
Шаг 6: TransportRegistry           (зависит от TransportSerializer)
Шаг 7: UriExporter                 (зависит от TransportRegistry + CapabilityModel)
Шаг 8: ExporterRegistry            (регистрирует уже готовый UriExporter)
Шаг 9: SubscriptionBuilder         (зависит от ExporterRegistry + CapabilityRegistry)
Шаг 10: Integration                (зависит от SubscriptionBuilder)
Шаг 11: Replace build_uri          (зависит от UriExporter)
Шаг 12: Remove legacy              (всё завершено)
```

**Изменение:** ExporterRegistry перенесён после UriExporter. Это устраняет циклическую зависимость.

### 1.4 Checkpoint'ы

| Checkpoint | Шаг | Критерий |
|---|---|---|
| CP-01 | Шаг 1 | UriValueSerializer даёт валидный JSON для всех типов (str, int, dict, list, bool) |
| CP-02 | Шаг 4 | TransportSerializer для xHTTP производит корректный dict |
| CP-03 | Шаг 7 | UriExporter генерирует URI, идентичный старому _build_vless_uri() |
| CP-04 | Шаг 9 | SubscriptionBuilder собирает subscription для 3 клиентов |
| CP-05 | Шаг 11 | 100% production-трафика идёт через новую архитектуру |
| CP-06 | Шаг 12 | Legacy-код удалён, тесты проходят |

### 1.5 Основные риски

| Риск | Этап | Митигация |
|---|---|---|
| UriValueSerializer меняет формат выходного URI | Шаг 1 | Сравнение до/после на всех существующих конфигах |
| TransportConfig не покрывает все поля inbound.json | Шаг 2 | Аудит полей inbound.json перед реализацией |
| CapabilityModel не хватает для клиента | Шаг 3 | Capability — enum, расширяется без изменения кода |
| UriExporter URI отличается от старого | Шаг 7 | Параллельный прогон, логирование различий |
| SubscriptionBuilder не обрабатывает ?format= | Шаг 9 | Тесты с разными значениями format |

---

## 2. Анализ точек интеграции

### 2.1 Таблица существующих файлов

| Файл | Действие | Причина |
|---|---|---|
| `app/__init__.py` | Без изменений | Пустой, только маркер пакета |
| `app/database.py` | Без изменений | Инфраструктура БД, не связана с URI/экспортом |
| `app/main.py` | Модификация | Добавить инициализацию Registry и запуск subscription server |
| `app/models/__init__.py` | Без изменений | Пустой |
| `app/models/vpn_client.py` | Без изменений | Доменная модель, не связана с архитектурой экспорта |
| `app/services/__init__.py` | Модификация | Импорт Registry и bootstrap-функций |
| `app/services/singbox_client_db_service.py` | Модификация | Замена _build_vless_uri() на вызов UriExporter |
| `app/services/singbox_client_service.py` | Модификация | Замена _build_vless_uri() — устранить дубль |
| `app/services/singbox_config_service.py` | Без изменений | Config manipulation, не связана с экспортом |
| `app/services/vpn_client_repository.py` | Без изменений | Data access, не связана с экспортом |
| `bot.py` | Без изменений | Telegram bot, не связан с архитектурой |
| `scripts/singbox_prepare_client_apply.py` | Без изменений | Deployment pipeline, не связан |
| `scripts/singbox_apply_pending_client.py` | Без изменений | Deployment pipeline, не связан |
| `scripts/singbox_full_pipeline_dry_run.py` | Без изменений | Deployment pipeline, не связан |
| `tests/test_singbox_client_service.py` | Дополнение | Добавить тесты для новой архитектуры; старые тесты остаются |
| `tests/test_singbox_prepare_client_apply.py` | Без изменений | Deployment tests |
| `tests/test_singbox_apply_pending_client.py` | Без изменений | Deployment tests |
| `tests/test_singbox_full_pipeline.py` | Без изменений | Integration tests |

### 2.2 Новые файлы (создаются в PHASE-04.3)

| Файл | Назначение |
|---|---|
| `app/services/uri_value_serializer.py` | UriValueSerializer |
| `app/services/transport_config.py` | TransportConfig иерархия |
| `app/services/transport_serializer.py` | TransportSerializer protocol |
| `app/services/capability_model.py` | CapabilityModel, Capability enum |
| `app/services/capability_registry.py` | CapabilityRegistry |
| `app/services/transport_registry.py` | TransportRegistry |
| `app/services/exporter_registry.py` | ExporterRegistry |
| `app/services/uri_exporter.py` | UriExporter |
| `app/services/exporter.py` | Exporter protocol |
| `app/services/subscription_builder.py` | SubscriptionBuilder |
| `app/services/capability_validator.py` | CapabilityValidator |
| `app/serializers/__init__.py` | Пакет serializers |
| `app/serializers/xhttp_serializer.py` | XHttpSerializer |
| `app/serializers/ws_serializer.py` | WebSocketSerializer |
| `app/serializers/grpc_serializer.py` | GrpcSerializer |
| `app/exporters/__init__.py` | Пакет exporters |
| `app/exporters/json_exporter.py` | JsonExporter |
| `app/exporters/yaml_exporter.py` | YamlExporter |
| `app/capabilities/__init__.py` | Пакет capability profiles |
| `app/capabilities/v2rayn.py` | V2RayNG capability profile |
| `app/capabilities/singbox.py` | sing-box capability profile |
| `app/capabilities/hiddify.py` | Hiddify capability profile |
| `app/_bootstrap.py` | Composition root — инициализация Registry |

---

## 3. Legacy Exit Plan

### 3.1 Компоненты на замену

| Legacy-компонент | Файл | Замена | Почему остаётся временно |
|---|---|---|---|
| `_build_vless_uri()` | `singbox_client_db_service.py:36-71` | UriExporter | Параллельный прогон для верификации |
| `_build_vless_uri()` | `singbox_client_service.py:72-96` | UriExporter | Дубль, удаляется синхронно с первым |
| Inbound-парсинг (дубли) | Оба сервиса + config_service | InboundParser (новый) | Требуется рефакторинг (PHASE-05) |

### 3.2 План удаления

| Компонент | Кто переходит на новый | Критерий удаления | Фаза | Момент |
|---|---|---|---|---|
| `_build_vless_uri()` (db_service) | SingBoxClientDbService | UriExporter URI совпадает 100% за 7 дней | Фаза 2 | Конец недели 3 |
| `_build_vless_uri()` (service) | SingBoxClientService | После удаления из db_service | Фаза 2 | Синхронно с db_service |
| Inbound-парсинг (дубли) | Все сервисы | InboundParser реализован и протестирован | PHASE-05 | Определяется отдельно |

### 3.3 Запрет бессрочного хранения

Legacy `_build_vless_uri()` удаляется не позднее чем через 30 дней после перехода 100% трафика на UriExporter. Если через 30 дней legacy не удалён — это считается архитектурной ошибкой и требует отдельного ADR.

---

## 4. Контроль обратной совместимости

### 4.1 Временная шкала

```
Фаза 1 (неделя 1-2):
  Старый _build_vless_uri() — ОСНОВНОЙ (100% трафика)
  Новый UriExporter — PARALLEL (логирование, сравнение)
  Feature-flag: export.new_architecture = false

Фаза 2 (неделя 3):
  Старый _build_vless_uri() — FALLBACK (0-100% по флагу)
  Новый UriExporter — ОСНОВНОЙ (10% → 50% → 100%)
  Feature-flag: export.new_architecture = true (gradual)
  Мониторинг: errors, latency, URI format diff

Фаза 3 (неделя 4):
  Старый _build_vless_uri() — ЗАМОРОЖЕН (никто не вызывает)
  Feature-flag: export.new_architecture = true (100%)
  Начало подготовки к удалению

Фаза 4 (неделя 5-6):
  Старый _build_vless_uri() — УДАЛЁН
  Feature-flag: удалён
```

### 4.2 Механизм проверки идентичности

В Фазе 1 оба URI (старый и новый) вычисляются для каждого запроса. Результаты сравниваются:

```
if old_uri != new_uri:
    log.warning("URI mismatch",
        inbound=inbound_tag,
        uuid=uuid,
        old=old_uri,
        new=new_uri,
        diff=compute_diff(old_uri, new_uri),
    )
```

Порог: 0 расхождений за 7 дней → переход к Фазе 2.

---

## 5. Dependency Injection Review

### 5.1 Проверка Architecture v1.0.1 раздел 5

- **Жизненный цикл:** описан концептуально (Singleton, Request-scoped, Stateless) — допускается
- **UML/ASCII-граф:** нарисован — допускается
- **Псевдокод инициализации:** ранее содержал сигнатуры и конструкции Python (нарушение границы)

### 5.2 Устранение нарушения

**Статус: ИСПРАВЛЕНО в PHASE-04.2.3.**

Production-level Python-код в разделе 5.4 Architecture v1.0.1 заменён на концептуальное описание:

```
Вместо:
  def init_dependencies():
      global capability_registry
      capability_registry = CapabilityRegistry()
      ...

Теперь:
  При старте приложения:
    1. Создать CapabilityRegistry
    2. Зарегистрировать профили: V2RayNG, sing-box, Hiddify
    3. Создать TransportRegistry
    4. Зарегистрировать сериализаторы: xHTTP, WebSocket, gRPC
    5. Создать UriExporter с TransportRegistry
    6. Создать ExporterRegistry
    7. Зарегистрировать экспортёры: uri, json, yaml
    8. CapabilityValidator — stateless, не требует инициализации
```

Все остальные секции Architecture v1.0.1 (1.3, 1.4, 1.5, 2.3, 2.4, 2.5, 3.1-3.6, 4.1, 4.3) также очищены от production-level Python-кода.

**Итог: Architecture v1.0.1 полностью соответствует границе между проектированием и реализацией.**

---

## 6. Production Safety Checklist

### 6.1 SOLID

| Принцип | Статус | Подтверждение |
|---|---|---|
| Single Responsibility | ✓ | Каждый компонент имеет одну зону ответственности |
| Open/Closed | ✓ | Новые транспорты/клиенты/форматы без изменения production-кода |
| Liskov Substitution | ✓ | Все TransportSerializer взаимозаменяемы (один Protocol) |
| Interface Segregation | ✓ | Exporter: 1 метод, TransportSerializer: 2 метода |
| Dependency Inversion | ✓ | UriExporter зависит от TransportRegistry (абстракция) |

### 6.2 Архитектурные проверки

| Проверка | Статус |
|---|---|
| Отсутствуют нарушения OCP | ✓ |
| Отсутствуют нарушения контрактов | ✓ |
| Отсутствуют циклические зависимости | ✓ (после переноса ExporterRegistry) |
| Отсутствуют скрытые зависимости | ✓ |
| Отсутствуют mutable global singleton | ✓ (Registry хранят ссылки, но не мутируют после bootstrap) |
| Отсутствует дублирование сериализации | ✓ |
| Отсутствует дублирование Capability | ✓ |
| Отсутствует дублирование Exporter | ✓ |
| Отсутствует дублирование Registry | ✓ |
| Отсутствуют скрытые точки расширения | ✓ |
| Отсутствуют нарушения Architecture Constraints | ✓ |
| Registry не зависят друг от друга | ✓ |
| CapabilityModel не зависит от TransportSerializer | ✓ |

---

## 7. План тестирования

### 7.1 Unit Tests

| Раздел | Что проверяется |
|---|---|
| **UriValueSerializer** | - str → корректное строковое значение (без кавычек)\n- int → str(int)\n- bool → true/false (lowercase)\n- dict → json.dumps(..., separators=(",",":"))\n- list → json.dumps(..., separators=(",",":"))\n- None → пустая строка\n- вложенные структуры → валидный JSON\n- граничные случаи: пустой dict, пустой list, спецсимволы |
| **TransportConfig** | - создание конфига с обязательными полями\n- создание с опциональными полями (значения по умолчанию)\n- неизменяемость после создания (frozen)\n- типобезопасность (проверка mypy/pyright) |
| **CapabilityModel** | - создание с набором capability\n- проверка наличия capability (in)\n- пересечение множеств capability\n- сериализация/десериализация |
| **CapabilityValidator** | - корректная конфигурация → valid=True\n- отсутствие формата вывода → ошибка\n- нарушение зависимости (FLOW без EXTRA) → ошибка\n- транспорт требует capability, которой нет у клиента → ошибка |
| **ExporterRegistry** | - регистрация экспортёра\n- получение по имени (существующее)\n- получение по имени (несуществующее) → None\n- повторная регистрация (перезапись/ошибка — по спецификации) |
| **TransportRegistry** | - регистрация сериализатора\n- получение по имени транспорта\n- serialize через registry |

### 7.2 Integration Tests

| Раздел | Что проверяется |
|---|---|
| **UriExporter + TransportRegistry** | - xHTTP transport → полный URI со всеми параметрами\n- WebSocket transport → URI с ws(s) параметрами\n- gRPC transport → URI с gRPC serviceName\n- transport с extra → JSON в query\n- transport без extra → flat params |
| **SubscriptionBuilder + ExporterRegistry** | - ?format=uri → возвращает URI\n- ?format=json → возвращает JSON\n- ?format=yaml → возвращает YAML\n- ?format=unsupported → ошибка/fallback |
| **CapabilityRegistry + UriExporter** | - V2RayNG profile → URI без downloadSettings\n- Hiddify profile → URI с downloadSettings |
| **InboundParser + TransportConfig** | - inbound.json (xHTTP) → корректный TransportConfig\n- inbound.json (WebSocket) → корректный TransportConfig |

### 7.3 Regression Tests

| Раздел | Что проверяется |
|---|---|
| **URI совпадение** | Новый UriExporter даёт тот же URI, что и старый _build_vless_uri() для всех существующих конфигов |
| **Dry-run pipeline** | После замены _build_vless_uri() dry-run не сломан |
| **Create client flow** | Создание клиента через SingBoxClientDbService с новой архитектурой |
| **User-Agent fallback** | ?format= по-прежнему работает; без ?format — fallback не сломан |

### 7.4 Compatibility Tests

| Раздел | Что проверяется |
|---|---|
| **V2RayNG** | URI открывается в V2RayNG (Android) |
| **V2RayN** | URI открывается в V2RayN (Windows) |
| **Hiddify** | URI открывается в Hiddify |
| **Sing-box** | URI открывается в sing-box |
| **NekoBox** | URI открывается в NekoBox |

### 7.5 Subscription Tests

| Раздел | Что проверяется |
|---|---|
| **Single config** | Subscription с одной конфигурацией |
| **Multiple configs** | Subscription с несколькими конфигурациями |
| **Mix transports** | Subscription с разными транспортами |
| **Format selection** | ?format=uri, json, yaml |
| **User-Agent header** | Fallback при отсутствии ?format= |
| **Error handling** | Некорректный ?format=, отсутствие конфигов |

### 7.6 Transport-specific Tests

| Раздел | Что проверяется |
|---|---|
| **xHTTP** | host, port, uuid, path, flow, encryption, extra (JSON), downloadSettings |
| **WebSocket** | host, port, uuid, path (ws://), headers, earlyData |
| **gRPC** | host, port, uuid, serviceName, multiMode |
| **REALITY** | host, port, uuid, flow, publicKey, shortId, spiderX, fingerprint |
| **Hysteria2** | host, port, password, obfs, sni, downloadSettings |
| **TUIC** | host, port, uuid, password, congestionControl, heartbeat, downloadSettings |

---

## 8. Production Rollback Plan

### 8.1 Сценарий отката

Если реализация PHASE-04.3 будет остановлена на любом этапе, проект возвращается к текущей стабильной версии (состояние на дату утверждения Architecture v1.0.1) следующими шагами.

### 8.2 Пошаговый сценарий

```
Шаг 1: Отключить subscription server (если запущен)
  - systemctl stop vpn-subscription-server
  - systemctl disable vpn-subscription-server

Шаг 2: Восстановить feature-flag
  - export NEW_ARCHITECTURE=false
  - Если флаг не был введён — ничего не делать

Шаг 3: Проверить старый _build_vless_uri()
  - Убедиться, что код в singbox_client_db_service.py не изменён
  - Если изменён — git checkout -- app/services/singbox_client_db_service.py
  - Аналогично для singbox_client_service.py

Шаг 4: Удалить новые файлы (если созданы)
  - git clean -fd app/services/uri_*.py
  - git clean -fd app/serializers/
  - git clean -fd app/exporters/
  - git clean -fd app/capabilities/
  - git clean -fd app/_bootstrap.py

Шаг 5: Удалить новые пакеты
  - Удалить app/serializers/__init__.py
  - Удалить app/exporters/__init__.py
  - Удалить app/capabilities/__init__.py

Шаг 6: Восстановить app/main.py
  - git checkout -- app/main.py
  - Удалить импорты новых компонентов

Шаг 7: Проверить тесты
  - pytest tests/ — все старые тесты проходят
  - Старые тесты не изменялись

Шаг 8: Проверить production pipeline
  - Запустить scripts/singbox_full_pipeline_dry_run.py
  - Создать тестового клиента
  - Проверить URI

Шаг 9: git commit отката (опционально)
  - Если были изменения в production-ветке — откатить коммит
  - git revert HEAD  # если был коммит
```

### 8.3 Время восстановления

| Этап | Время |
|---|---|
| Отключение subscription server | 1 минута |
| Восстановление файлов | 5 минут |
| Проверка тестов | 5 минут |
| Проверка pipeline | 10 минут |
| **Итого** | **~20 минут** |

### 8.4 Критерии остановки

Реализация останавливается, если:
- URI-формат расходится со старым более чем на 5 дней
- Subscription server вызывает ошибки у >1% пользователей
- Новая архитектура не достигает feature parity за 3 недели
- Обнаружено архитектурное ограничение, требующее изменения ADR-001 — ADR-006

---

## 9. Performance Review

### 9.1 Оценка сложности

| Операция | Асимптотическая сложность | Ожидаемое время |
|---|---|---|
| Создание одной URI | O(T) — T = transport serializer lookup (O(1)) + serialize (O(1)) + format URI (O(1)) | < 1 мс |
| Генерация одной подписки (N configs) | O(N) — N × O(URI) | < N × 1 мс |
| Экспорт 100 конфигураций | O(100) | < 100 мс |
| Экспорт 1000 конфигураций | O(1000) | < 1 с |

### 9.2 Потенциальные узкие места

| Узел | Причина | Митигация |
|---|---|---|
| TransportRegistry.get() | dict lookup O(1), не является узким местом | Не требуется |
| UriExporter.serialize() | json.dumps() для extra-параметров | Оптимизация не требуется для типовых размеров |
| SubscriptionBuilder | Сборка строки из N конфигураций (конкатенация) | Использовать join() для URI, генераторы для JSON/YAML |
| QR Exporter | Генерация QR-кода (если будет добавлен) | Асинхронная генерация, кэширование |

### 9.3 Точки масштабирования

- **Кэширование:** Готовая subscription-строка может кэшироваться по хешу набора конфигов. Сброс кэша при изменении любого конфига.
- **Потоковая передача:** Для JSON/YAML экспорта 1000+ конфигов — использовать генераторы/streaming вместо полной сборки в памяти.
- **Параллельная сериализация:** N конфигов можно сериализовать параллельно через ThreadPoolExecutor (т.к. сериализация CPU-bound, но без блокировок — GIL не проблема для json.dumps).

### 9.4 Бюджет производительности

| Метрика | Цель |
|---|---|
| URI latency (p50) | < 2 мс |
| URI latency (p99) | < 10 мс |
| Subscription 100 configs (p50) | < 200 мс |
| Subscription 1000 configs (p50) | < 2 с |
| Memory per subscription (100 configs) | < 10 MB |

---

## 10. Code Quality Rules

### 10.1 Обязательные правила для PHASE-04.3

| № | Правило | Обоснование |
|---|---|---|
| 1 | **dataclass вместо dict** | Типобезопасность, IDE support, предсказуемая сериализация |
| 2 | **Строгая типизация** | Все параметры методов и полей моделей имеют type hints |
| 3 | **Запрет Any** | Исключение только с явным `# type: ignore[override]` и комментарием причины |
| 4 | **Запрет скрытых преобразований** | str(v), int(v) без явного контракта — запрещены |
| 5 | **Запрет магических строк** | Все строковые литералы — константы/Enum |
| 6 | **Запрет магических чисел** | Все числовые литералы — именованные константы |
| 7 | **Обязательные type hints** | Каждый метод, каждый параметр, каждое поле |
| 8 | **Immutable Models** | TransportConfig — frozen=True. CapabilityModel — immutable по построению |
| 9 | **Composition over Inheritance** | Protocol/ABC вместо глубокой иерархии наследования |
| 10 | **Dependency Inversion** | Зависимость от абстракций, не от конкретных реализаций |
| 11 | **Fail Fast** | Валидация на границе: проверять входные данные сразу |
| 12 | **Explicit Types** | Никаких duck-typing на границах модулей |
| 13 | **No Reflection** | Никаких getattr/hasattr для динамической диспетчеризации |
| 14 | **No Hidden Magic** | Никаких __init_subclass__, metaclass, динамической генерации |
| 15 | **No Global State** | Registry — явные объекты, не глобальные переменные с мутацией после bootstrap |
| 16 | **No Runtime Monkey Patching** | Никакой замены методов после инициализации |

### 10.2 Инструменты контроля

| Инструмент | Команда | Применение |
|---|---|---|
| mypy / pyright | `mypy app/` | Статическая типизация |
| ruff | `ruff check app/` | Lint |
| pytest | `pytest tests/` | Тесты |
| pre-commit | `pre-commit run --all-files` | Перед каждым коммитом |

### 10.3 Порог качества

| Метрика | Минимум |
|---|---|
| type check | 0 ошибок mypy |
| lint | 0 ошибок ruff |
| test coverage (unit) | > 90% для нового кода |
| test coverage (integration) | > 80% для нового кода |
| тесты проходят | 100% |

---

## 11. ARCHITECTURE FREEZE CONFIRMATION

### 11.1 Формальное подтверждение

```
┌─────────────────────────────────────────────────────────────────────┐
│                    ARCHITECTURE FREEZE                              │
│                                                                     │
│  Architecture v1.0.1 ________________________________ ЗАМОРОЖЕНА    │
│  (ARCHITECTURE_v1.0.1.md)                                           │
│                                                                     │
│  Статус: ✓ окончательно заморожена                                  │
│                                                                     │
│  Правила:                                                           │
│  • Все будущие архитектурные изменения — ТОЛЬКО через новый ADR     │
│  • PHASE-04.3 является исключительно ЭТАПОМ РЕАЛИЗАЦИИ              │
│  • Во время PHASE-04.3 ЗАПРЕЩЕНО изменять архитектуру               │
│    без отдельного архитектурного этапа                              │
│                                                                     │
│  Нарушение: любое изменение в Architecture v1.0.1 без ADR           │
│  считается архитектурной ошибкой                                    │
└─────────────────────────────────────────────────────────────────────┘
```

### 11.2 Подтверждение

| Пункт | Статус |
|---|---|
| Architecture v1.0.1 окончательно заморожена | ✓ |
| Все будущие изменения — только через ADR | ✓ |
| PHASE-04.3 — только реализация | ✓ |
| Во время PHASE-04.3 запрещено менять архитектуру без ADR | ✓ |

---

## 12. FINAL GO / NO GO

### 12.1 Решение

# GO

### 12.2 Обоснование

Производственная разработка может быть начата, потому что:

1. **Архитектура завершена** — Architecture v1.0.1 заморожена. Все 12 разделов аудита пройдены. Нет открытых архитектурных вопросов.

2. **План реализации безопасен** — UriValueSerializer фиксит BUG-001 первым шагом. UriExporter проходит параллельный прогон со старым кодом. Полный откат возможен за 20 минут.

3. **OCP соблюдён** — новые транспорты, клиенты и форматы требуют только регистрации в composition root. Проверено на 4 сценариях.

4. **Риски низкие (LOW)** — таксономия Capability расширяема, все Registry используют O(1) lookup, откат тривиален.

5. **Legacy exit спланирован** — 4 фазы с чёткими критериями удаления. Бесконечное сосуществование исключено.

### 12.3 Итоговые метрики

| Метрика | Значение |
|---|---|
| **Готовность** | 98% |
| **Архитектурный риск** | LOW |
| **Рекомендация** | START IMPLEMENTATION |
| **Первый шаг** | UriValueSerializer |

### 12.4 Что может потребовать пересмотра через год

- Если появится transport с принципиально новым форматом сериализации, не вписывающимся в dict → может потребоваться новый Exporter.
- Если CapabilityModel разрастётся до 50+ значений → может потребоваться категоризация/группировка capability.
- Если потребуется динамическая загрузка транспортов из внешних модулей → Registry нужно адаптировать под plugin-architecture.

Ни один из этих сценариев не требует переписывания. Все решаются расширением в рамках текущей архитектуры.

### 12.5 Рекомендации перед PHASE-04.3

1. Начать с UriValueSerializer — изолированный фикс BUG-001
2. Реализовать TransportConfig + CapabilityModel параллельно
3. Первый checkpoint — UriExporter URI совпадает со старым
4. Не вводить subscription server в production до проверки совпадения URI
5. Фиксировать все расхождения URI в логах для анализа

---

*Конец документа Production Readiness Review v1.0*
