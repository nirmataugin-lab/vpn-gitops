# Architecture v1.0.1
## Финальный архитектурный аудит

**Дата:** 2026-07-29
**Версия:** 1.0.1
**Статус:** Утверждена
**Предыдущая версия:** 1.0.0

---

## Содержание

0. Architecture Decision Records (ADR)
1. Exporter Registry
2. Transport Registry
3. Capability Validation
4. Версионирование моделей
5. Dependency Injection
6. Финальная проверка OCP
7. Architecture Constraints
8. Backward Compatibility
9. Definition of Done
10. FINAL ENGINEERING REVIEW

---

## 0. Architecture Decision Records (ADR)

### ADR-001: Выбор Capability-based подхода

**Контекст**

Необходимо сопоставлять transports (xHTTP, WebSocket, gRPC, Hysteria2, TUIC, WireGuard, Shadowsocks, Trojan, VLESS, VMess) с clients (V2RayNG, V2RayN, V2RayTun, Hiddify, Streisand, NekoBox, FoXray, Clash, sing-box) так, чтобы добавление нового transport ИЛИ нового client не требовало изменения существующего кода. Прямое декартово произведение даёт O(N×M) комбинаций.

**Рассматриваемые варианты**

1. **Оригинальный 3-уровневый подход** — Transport → Intermediate Format → Client Format. Каждый transport знает о каждом intermediate, каждый client знает о каждом intermediate. Всё равно O(N×M) при добавлении нового transport или client.

2. **Capability-based подход** — Каждый transport декларирует, какие возможности ему нужны (flat_params, extra, download_settings, etc.). Каждый client декларирует, какие возможности поддерживает. Экспортёр принимает решение на основе пересечения возможностей. Сложность O(N+M).

3. **Visitor Pipeline** — TransportVisitor с visit_* для каждого transport. Нарушает OCP: новый transport требует нового метода в Visitor.

**Принятое решение**

Capability-based подход (вариант 2).

**Последствия**

- Сложность масштабирования линейная: O(N+M) вместо O(N×M)
- TransportSerializer сериализует transport в dict и указывает, какие capabilities необходимы
- Client не привязан к transport напрямую; client определяет только свой профиль возможностей
- UriExporter один для всех URI-клиентов, параметризован CapabilityModel (данные, а не код)

**Недостатки**

- Необходимо поддерживать и развивать таксономию capability (риск разрастания)
- Некоторые редкие комбинации transport+client могут потребовать введения новой capability
- Для отладки сложнее трассировать, почему конкретная пара transport+client несовместима

---

### ADR-002: Единый UriExporter вместо множества ClientExporter'ов

**Контекст**

В архитектуре фигурировала идея создать отдельный ClientExporter для каждого клиента (V2RayNGExporter, HiddifyExporter, etc.). Все URI-клиенты используют одинаковый URI-формат (scheme://uuid@host:port?params) и отличаются только набором поддерживаемых query-параметров.

**Рассматриваемые варианты**

1. **Множество ClientExporter'ов** — Каждый клиент = свой класс экспорта. Рост числа экспортёров = O(N) по числу клиентов. Дублирование логики построения URI.

2. **Единый UriExporter + CapabilityModel** — Один класс UriExporter, параметризованный CapabilityModel (данные). Каждый URI-клиент описывается профилем capability, а не кодом.

**Принятое решение**

Единый UriExporter (вариант 2).

**Последствия**

- UriExporter не требует изменений при добавлении нового URI-клиента
- Новый URI-клиент = только регистрация CapabilityModel (данные, а не код)
- Единая точка тестирования URI-экспорта
- Логика построения URI не дублируется

**Недостатки**

- UriExporter должен поддерживать все возможные URI-вариации (что усложняет один класс)
- Если у клиента принципиально другой формат URI (нестандартный), потребуется отдельный Exporter
- CapabilityModel может стать слишком детальным для покрытия всех edge case'ов

---

### ADR-003: Отказ от ClientExporter как концепции

**Контекст**

Термин "ClientExporter" предполагал класс, который знает и о transport, и о client, и о формате экспорта. Это создавало риск O(N×M) комбинаций.

**Рассматриваемые варианты**

1. **ClientExporter** — инкапсулирует логику экспорта для пары (client, transport)
2. **Разделение: TransportSerializer + Exporter** — TransportSerializer знает только о transport. Exporter знает только о формате экспорта (URI, JSON, YAML). Client представлен только CapabilityModel (данные).

**Принятое решение**

ClientExporter как отдельная сущность отсутствует. Вместо него:
- **TransportSerializer** — сериализует transport в структурированный dict
- **Exporter** — преобразует dict в выходной формат (URI/JSON/YAML)
- **CapabilityModel** — определяет, какие поля и как exporter должен обрабатывать (данные)

**Последствия**

- Количество Exporters = количество форматов (URI, JSON, YAML, QR), а не количество клиентов
- TransportSerializers и Exporters ортогональны: можно комбинировать любые пары
- CapabilityModel служит единственным "мостиком" между transport и client

**Недостатки**

- Требуется чёткая спецификация, какие capability влияют на какие аспекты экспорта
- CapabilityModel может не покрыть все client-specific edge case'ы (тогда нужен хардкод в Exporter)

---

### ADR-004: Запрет dict[str, Any] без формального контракта

**Контекст**

Типичная ошибка в VPN-проектах: параметры транспорта передаются как неструктурированные словари, что приводит к ошибкам времени выполнения, невозможности статического анализа и отсутствию документации контрактов.

**Рассматриваемые варианты**

1. **dict[str, Any]** — гибко, но небезопасно. Ошибки обнаруживаются только в рантайме.
2. **Typed TransportConfig** — система датаклассов/Pydantic с типизированными полями. Каждый transport имеет свой датакласс с конкретными полями.

**Принятое решение**

Типизированные TransportConfig (вариант 2). Каждый transport определяет свой датакласс-конфиг с конкретными типами полей. Никаких catch-all полей.

**Последствия**

- Статическая типизация: IDE, mypy, pyright
- Самодокументируемые контракты
- Сериализация предсказуема: нет сюрпризов с str(v)
- BUG-001 (str(v) вместо json.dumps) становится невозможен по построению

**Недостатки**

- Больше boilerplate-кода для определения конфигов
- При добавлении поля нужно менять датакласс (что естественно, но требует осознания)

---

### ADR-005: User-Agent не является основным механизмом выбора формата

**Контекст**

В существующих решениях (например, V2Ray subscription) выбор формата ответа часто определяется по User-Agent запроса. Это ненадёжно: User-Agent легко подделать, может отсутствовать, меняется между версиями клиента.

**Рассматриваемые варианты**

1. **User-Agent primary** — определение клиента по User-Agent, выбор формата на основе этого
2. **?format= primary** — обязательный query-параметр для выбора формата; User-Agent только как fallback-хинт

**Принятое решение**

Параметр `?format=` является основным механизмом выбора формата ответа. User-Agent используется только как fallback-хинт, когда ?format отсутствует.

**Последствия**

- Явное указание формата: предсказуемое поведение
- User-Agent перестаёт быть точкой отказа
- Возможность кэширования ответов по format
- Все URI-клиенты получают одинаковый URI (что корректно)

**Недостатки**

- Legacy-клиенты, которые не шлют ?format, требуют fallback по User-Agent
- Некоторые клиенты могут не поддерживать кастомные query-параметры в subscription URL

---

### ADR-006: Registry вместо switch / if / elif

**Контекст**

Добавление нового транспорта или нового формата экспорта не должно приводить к изменению существующего кода. Конструкции switch/if-elif нарушают Open/Closed Principle: каждое добавление требует редактирования существующего файла.

**Рассматриваемые варианты**

1. **switch / if / elif** — просто, но каждое добавление требует изменения production-кода
2. **Registry + dict lookup** — регистрация обработчиков в словаре при старте приложения. Добавление = новый файл + строчка регистрации.

**Принятое решение**

Registry pattern (вариант 2). Три registry:
- `TransportRegistry` — регистрация TransportSerializer по имени транспорта
- `ExporterRegistry` — регистрация Exporter по имени формата
- `CapabilityRegistry` — регистрация CapabilityModel по идентификатору клиента

Регистрация выполняется однократно при старте приложения (import-time или explicit bootstrap).

**Последствия**

- Истинное соблюдение OCP: существующий production-код не изменяется
- Добавление = register() или import в точке сборки
- Легко тестировать: registry можно изолированно заполнить тестовыми данными

**Недостатки**

- Косвенная диспетчеризация: сложнее понять поток выполнения без отладчика
- Необходимо гарантировать, что registry заполнен до первого запроса (ошибка порядка инициализации)
- Нет compile-time проверки, что все транспорты зарегистрированы

---

## 1. Exporter Registry

### 1.1 Назначение

ExporterRegistry управляет коллекцией Exporter'ов — компонентов, преобразующих структурированные данные (dict) в выходной формат (URI, JSON, YAML, QR-код и т.д.).

Каждый Exporter реализует единый интерфейс и зарегистрирован под ключом — названием формата.

### 1.2 UML-диаграмма

```
┌─────────────────────────────────────────────────────────────────────┐
│                        ExporterRegistry                             │
├─────────────────────────────────────────────────────────────────────┤
│ - _exporters: dict[str, Exporter]                                   │
├─────────────────────────────────────────────────────────────────────┤
│ + register(name: str, exporter: Exporter) -> None                   │
│ + get(name: str) -> Exporter | None                                 │
│ + get_all() -> dict[str, Exporter]                                  │
│ + has(name: str) -> bool                                            │
│ + export(name: str, data: dict, capability: CapabilityModel) -> str │
└─────────────────────────────────────────────────────────────────────┘
                                │
                                │ 1
                                │ implements
                                ▼
                 ┌─────────────────────────────┐
                 │   Exporter (Protocol/ABC)   │
                 ├─────────────────────────────┤
                 │ + export(data: dict,        │
                 │         capability:         │
                 │           CapabilityModel)  │
                 │       -> str                │
                 └─────────────────────────────┘
                                ▲
            ┌───────────────────┼───────────────────┐
            │                   │                    │
     ┌──────┴──────┐    ┌──────┴──────┐     ┌───────┴───────┐
     │ UriExporter │    │JsonExporter │     │YamlExporter   │
     └─────────────┘    └─────────────┘     └───────────────┘
```

### 1.3 Контракт Exporter

Контракт Exporter описывается набором операций (не class, а логическое соглашение):

```
ВХОД:  data (dict) — структурированные параметры конфигурации
       capability (CapabilityModel) — профиль возможностей клиента
ВЫХОД: str — конфигурация в целевом формате (URI, JSON, YAML, ...)
```

Каждый Exporter реализует эту операцию по-своему. Тип возвращаемого значения — всегда строка.

### 1.4 Регистрация Exporter'ов

Регистрация выполняется однократно при старте приложения:

```
1. Создать ExporterRegistry (пустой)
2. Создать UriExporter, JsonExporter, YamlExporter (каждый — отдельный экземпляр)
3. Зарегистрировать каждый в Registry под ключом-именем формата:
   - "uri"    → UriExporter
   - "json"   → JsonExporter
   - "yaml"   → YamlExporter
   - "qr"     → QrExporter (будущее расширение)
```

Все экспортёры создаются в одном месте — composition root. Никакой другой код не участвует в регистрации.

### 1.5 Пример добавления нового Exporter

**Сценарий: добавить поддержку TOML-формата.**

```
ШАГ 1: Создать новый модуль для TOML-экспортёра
       Модуль содержит одну операцию:
         ВХОД:  data (dict), capability (CapabilityModel)
         ВЫХОД: str (TOML-строка, полученная через tomli_w.dumps)

ШАГ 2: В composition root добавить одну строку:
         ExporterRegistry.register("toml", TomlExporter)

ШАГ 3: Никакой существующий production-код не изменяется.
```

Весь процесс: создать файл → добавить строку регистрации. Никаких изменений в существующих экспортёрах, сериализаторах или бизнес-логике.

---

## 2. Transport Registry

### 2.1 Назначение

TransportRegistry управляет коллекцией TransportSerializer'ов — компонентов, преобразующих параметры конкретного транспорта в типизированную структуру (TransportConfig) и затем в dict для экспортёра.

### 2.2 UML-диаграмма

```
┌─────────────────────────────────────────────────────────────────────┐
│                       TransportRegistry                             │
├─────────────────────────────────────────────────────────────────────┤
│ - _serializers: dict[str, TransportSerializer]                      │
├─────────────────────────────────────────────────────────────────────┤
│ + register(name: str, serializer: TransportSerializer) -> None      │
│ + get(name: str) -> TransportSerializer | None                      │
│ + get_all() -> dict[str, TransportSerializer]                       │
│ + has(name: str) -> bool                                            │
│ + serialize(name: str, config: TransportConfig) -> dict             │
└─────────────────────────────────────────────────────────────────────┘
                                │
                                │ 1
                                │ implements
                                ▼
            ┌─────────────────────────────────────────┐
            │      TransportSerializer (Protocol)     │
            ├─────────────────────────────────────────┤
            │ + serialize(config: TransportConfig)    │
            │       -> dict                           │
            │ + required_capabilities(config) ->      │
            │       set[Capability]                   │
            └─────────────────────────────────────────┘
                                ▲
            ┌───────────────────┼───────────────────────────┐
            │                   │                            │
    ┌───────┴────────┐  ┌──────┴───────┐         ┌──────────┴──────────┐
    │XHttpSerializer │  │ WsSerializer │   ...   │ Hysteria2Serializer │
    └────────────────┘  └──────────────┘         └─────────────────────┘
```

### 2.3 Контракт TransportSerializer

TransportSerializer — компонент с двумя операциями (концептуально):

```
Операция 1: serialize
  ВХОД:  config (TransportConfig) — типизированные параметры транспорта
  ВЫХОД: dict — структурированные данные, готовые для экспортёра

Операция 2: required_capabilities
  ВХОД:  config (TransportConfig)
  ВЫХОД: набор capability (множество строковых идентификаторов)
         — какие возможности клиента необходимы для экспорта этого транспорта
```

### 2.4 Регистрация сериализаторов

Все сериализаторы регистрируются в TransportRegistry при старте приложения:

| Ключ (transport name) | Сериализатор | Статус |
|---|---|---|
| `"xhttp"` | XHttpSerializer | PHASE-04.3 |
| `"ws"` | WebSocketSerializer | PHASE-04.3 |
| `"grpc"` | GrpcSerializer | PHASE-04.3 |
| `"httpupgrade"` | HttpUpgradeSerializer | PHASE-05 |
| `"reality"` | RealitySerializer | PHASE-05 |
| `"hysteria2"` | Hysteria2Serializer | PHASE-05 |
| `"tuic"` | TUICSerializer | PHASE-05 |
| `"trojan"` | TrojanSerializer | PHASE-05 |
| `"wireguard"` | WireGuardSerializer | PHASE-05 |
| `"shadowsocks"` | ShadowsocksSerializer | PHASE-05 |
| `"vless"` | VLessSerializer | PHASE-05 |
| `"vmess"` | VMessSerializer | PHASE-05 |

Регистрация выполняется в composition root последовательным вызовом:
для каждого транспорта — одна операция регистрации в TransportRegistry.

### 2.5 Пример добавления нового транспорта

**Сценарий: добавить поддержку транспорта QUIC-X.**

Новый транспорт требует двух артефактов:

**Артефакт 1 — Конфиг (TransportConfig):**
Типизированная структура с полями:
- host (строка)
- port (целое)
- uuid (строка)
- congestion_control (строка, по умолчанию "bbr")
- padding (логическое, по умолчанию false)

**Артефакт 2 — Сериализатор (TransportSerializer):**
Компонент с двумя операциями:
- serialize: преобразует QuicXConfig в dict с ключами: host, port, uuid, congestionControl, padding
- required_capabilities: возвращает набор {supports_uri, supports_extra}

**Регистрация:**
В composition root добавляется одна операция:
- TransportRegistry.register("quic-x", QuicXSerializer)

Никакой существующий production-код не изменяется. Ни один существующий сериализатор не требует изменений.

---

## 3. Capability Validation

### 3.1 Определение Capability

Capability — строковый идентификатор, представляющий одну атомарную возможность клиента или требования транспорта.

Категории capability:

| Категория | Capability | Описание |
|---|---|---|
| **Форматы вывода** | `supports_uri` | Клиент понимает URI-формат |
| | `supports_json` | Клиент понимает JSON-формат |
| | `supports_yaml` | Клиент понимает YAML-формат |
| | `supports_qr` | Клиент поддерживает QR-код |
| **Параметры URI** | `supports_flat_params` | Параметры через `?key=value` в URI |
| | `supports_extra` | JSON-объект `extra` в query-параметрах |
| | `supports_download_settings` | Параметры загрузки (dlConfig) |
| | `supports_xmux` | XMUX-настройки мультиплексирования |
| **Транспорты** | `supports_xhttp` | XHTTP транспорт |
| | `supports_ws` | WebSocket транспорт |
| | `supports_grpc` | gRPC транспорт |
| | `supports_httpupgrade` | HTTPUpgrade транспорт |
| | `supports_reality` | REALITY транспорт |
| | `supports_hysteria2` | Hysteria2 транспорт |
| | `supports_tuic` | TUIC транспорт |
| | `supports_trojan` | Trojan транспорт |
| | `supports_wireguard` | WireGuard транспорт |
| | `supports_shadowsocks` | Shadowsocks транспорт |
| **Особенности** | `requires_encryption` | Требуется шифрование |
| | `requires_tls` | Требуется TLS |
| | `supports_flow` | Поддержка flow (xtls-rprx-*) |
| | `supports_public_key` | Поддержка publicKey (REALITY) |
| | `supports_short_id` | Поддержка shortId (REALITY) |

### 3.2 Обязательные Capability

Каждый профиль клиента должен включать как минимум один формат вывода:

- Клиент должен содержать хотя бы один из: `supports_uri`, `supports_json`, `supports_yaml`
- Если ни один формат не указан — профиль считается некорректным

### 3.3 Несовместимые Capability

На текущем этапе нет строго несовместимых capability. Все перечисленные capability могут комбинироваться произвольно.

Правила несовместимости вводятся только при появлении конкретного конфликта (например, `supports_flat_params` и `supports_extra` могут конфликтовать для конкретного экспортёра — решение принимается на уровне Exporter, а не на уровне CapabilityModel).

### 3.4 Зависимости Capability

Некоторые capability требуют других capability. Правила зависимостей:

| Capability | Требует |
|---|---|
| `supports_xhttp` | `supports_extra` |
| `supports_grpc` | `supports_extra` |
| `supports_reality` | `supports_extra`, `supports_flow` |
| `supports_hysteria2` | `supports_extra` |
| `supports_tuic` | `supports_extra` |
| `supports_flow` | `supports_extra` |
| `supports_public_key` | `supports_extra` |
| `supports_short_id` | `supports_extra` |
| `supports_download_settings` | `supports_extra` |
| `supports_xmux` | `supports_extra` |

Если клиент указывает capability, но не указывает её зависимость — профиль некорректен.

### 3.5 Правила проверки Capability

Валидатор Capability — stateless-компонент, выполняющий три проверки:

```
ПРОВЕРКА 1: Совместимость транспорта и клиента
  Для каждой capability, требуемой транспортом:
    Если её нет в профиле клиента → ошибка

ПРОВЕРКА 2: Зависимости внутри профиля клиента
  Для каждой capability в профиле клиента:
    Если у неё есть зависимость, но dependency отсутствует в профиле → ошибка

ПРОВЕРКА 3: Наличие формата вывода
  Если в профиле нет ни одного из: supports_uri, supports_json, supports_yaml → ошибка
```

Результат валидации:
- **valid**: true/false
- **errors**: список строк с описанием ошибок (пустой, если valid)
- **warnings**: список предупреждений (не блокирует экспорт)

### 3.6 Примеры

#### Корректная конфигурация: V2RayNG v5 с xHTTP

Профиль клиента V2RayNG v5 содержит capability:
`{supports_uri, supports_extra, supports_xhttp, supports_flow}`

Транспорт xHTTP требует для экспорта:
`{supports_extra}`

Проверка: `{supports_extra} ⊆ {supports_uri, supports_extra, supports_xhttp, supports_flow}` → **совместимо.**

#### Некорректная конфигурация: Minimal Client без SUPPORTS_EXTRA + xHTTP

Профиль клиента:
`{supports_uri, supports_flat_params}`  (нет supports_extra)

Транспорт xHTTP требует:
`{supports_extra}`

Проверка: `{supports_extra} ⊈ {supports_uri, supports_flat_params}` → **ошибка:** "Transport requires supports_extra, not in client profile"

#### Ошибка валидации: отсутствие формата вывода

Профиль клиента пуст: `{}`

Проверка 3: нет ни supports_uri, ни supports_json, ни supports_yaml → **ошибка:** "Client must support at least one output format"

#### Ошибка валидации: нарушение зависимости

Профиль клиента:
`{supports_uri, supports_flow}` (supports_flow требует supports_extra, которого нет)

Проверка 2: supports_flow → требует supports_extra → отсутствует → **ошибка:** "supports_flow requires supports_extra, but supports_extra is missing"

---

## 4. Версионирование моделей

Архитектурный резерв. Полноценное версионирование отложено до PHASE-06.

### 4.1 Поля версий

В каждую модель включаются поля версий (как часть данных, не как отдельные классы):

| Модель | Поле | Тип | По умолчанию | Назначение |
|---|---|---|---|---|
| TransportConfig | schema_version | целое | 1 | Версия схемы TransportConfig |
| TransportConfig | transport_version | целое | 1 | Версия конкретного transport serializer |
| CapabilityModel | capability_version | целое | 1 | Версия таксономии capability |
| CapabilityModel | schema_version | целое | 1 | Версия схемы CapabilityModel |

### 4.2 Спецификация полей

| Поле | Тип | По умолчанию | Назначение | Использование | Миграция |
|---|---|---|---|---|---|
| `schema_version` | `int` | 1 | Версия структуры данных TransportConfig | При десериализации: если `schema_version` не совпадает с ожидаемой → применить мигратор | `SchemaMigrationRegistry` — регистрация функций `migrate_v1_to_v2(config) -> config` |
| `transport_version` | `int` | 1 | Версия параметров конкретного транспорта | TransportSerializer проверяет: если `transport_version` не совпадает → выбрать нужную версию сериализатора | Или versioned serializer через registry: `registry.get(f"xhttp/v2")` |
| `capability_version` | `int` | 1 | Версия таксономии capability | При сравнении наборов capability разных версий | Маппинг имён capability между версиями |

### 4.3 Предполагаемый механизм миграции

Механизм миграции зарезервирован архитектурно, но не реализуется до PHASE-06.

Концепция:

```
SchemaMigrationRegistry (контейнер функций миграции)
  - регистрация: привязать функцию миграции к паре (from_version, to_version)
  - выполнение: последовательно применить цепочку миграций от текущей версии до целевой
  - если миграция не найдена → ошибка "MigrationNotFound"

Пример цепочки:
  v1 → v2: добавить поле "flow" (по умолчанию пустая строка)
  v2 → v3: переименовать "password" в "auth_token"
```

Никакой production-код миграции не пишется до PHASE-06. Архитектурный резерв зафиксирован.

---

## 5. Dependency Injection

### 5.1 Жизненный цикл компонентов

```
                    ┌─────────────────────────────────────┐
                    │         Application Bootstrap        │
                    │         (main.py / lifespan)         │
                    └──────────────────┬──────────────────┘
                                       │
            ┌──────────────────────────┼──────────────────────────┐
            │                          │                          │
            ▼                          ▼                          ▼
    ┌───────────────┐        ┌──────────────────┐       ┌──────────────────┐
    │CapabilityReg. │◄───────│  TransportReg.   │       │ ExporterRegistry │
    │  (Singleton)  │        │  (Singleton)     │       │  (Singleton)     │
    └───────┬───────┘        └────────┬─────────┘       └────────┬─────────┘
            │                         │                          │
            │                         ▼                          │
            │                 ┌──────────────────┐               │
            │                 │  UriExporter     │───────────────►│
            │                 │  (Singleton)     │get_transporter │
            │                 └────────┬─────────┘               │
            │                          │                         │
            │                          ▼                         │
            │              ┌──────────────────────┐             │
            │              │  SubscriptionBuilder │             │
            │              │  (Request-scoped)    │─────────────►│
            │              └──────────────────────┘  get_exporter│
            │                         │                          │
            └─────────────────────────┼──────────────────────────┘
                  validate_capability │
                                      ▼
                          ┌──────────────────────┐
                          │  Response (str/bytes) │
                          └──────────────────────┘
```

### 5.2 Спецификация компонентов

| Компонент | Создаёт | Владеет | Паттерн | Время жизни | Зависимости |
|---|---|---|---|---|---|
| `CapabilityRegistry` | Application bootstrap | Application | Singleton | Всё время работы приложения | Нет |
| `TransportRegistry` | Application bootstrap | Application | Singleton | Всё время работы приложения | Нет |
| `ExporterRegistry` | Application bootstrap | Application | Singleton | Всё время работы приложения | Нет |
| `UriExporter` | Application bootstrap | Application | Singleton | Всё время работы приложения | TransportRegistry |
| `JsonExporter` | Application bootstrap | Application | Singleton | Всё время работы приложения | Нет |
| `YamlExporter` | Application bootstrap | Application | Singleton | Всё время работы приложения | Нет |
| `SubscriptionBuilder` | Request handler | Request handler | Per-request | Один HTTP-запрос | ExporterRegistry, CapabilityRegistry |
| `CapabilityValidator` | Прямой вызов | — | Stateless | Не хранит состояние | Нет |

### 5.3 ASCII Dependency Graph

```
Application Bootstrap
  ├── CapabilityRegistry (singleton, 0 dependencies)
  ├── TransportRegistry (singleton, 0 dependencies)
  ├── ExporterRegistry (singleton, 0 dependencies)
  ├── UriExporter (singleton, depends on TransportRegistry)
  ├── JsonExporter (singleton, 0 dependencies)
  └── YamlExporter (singleton, 0 dependencies)

HTTP Request Handler
  └── SubscriptionBuilder (request-scoped)
        ├── depends on ExporterRegistry (injected at construction)
        ├── depends on CapabilityRegistry (injected at construction)
        ├── calls: CapabilityValidator.validate()
        ├── calls: ExporterRegistry.export()
        └── returns: str (response body)
```

### 5.4 Порядок инициализации (концептуально)

При старте приложения компоненты создаются в строгом порядке:

```
ШАГ 1: Создать CapabilityRegistry
         → Зарегистрировать профили клиентов: V2RayNG, sing-box, Hiddify
ШАГ 2: Создать TransportRegistry
         → Зарегистрировать сериализаторы: xHTTP, WebSocket, gRPC
ШАГ 3: Создать UriExporter
         → Внедрить TransportRegistry (через конструктор)
ШАГ 4: Создать JsonExporter (stateless, без зависимостей)
ШАГ 5: Создать YamlExporter (stateless, без зависимостей)
ШАГ 6: Создать ExporterRegistry
         → Зарегистрировать UriExporter под ключом "uri"
         → Зарегистрировать JsonExporter под ключом "json"
         → Зарегистрировать YamlExporter под ключом "yaml"
ШАГ 7: CapabilityValidator — stateless, инициализация не требуется
```

Обработка каждого HTTP-запроса:

```
ШАГ 1: Создать SubscriptionBuilder
         → Внедрить CapabilityRegistry и ExporterRegistry
ШАГ 2: Вызвать SubscriptionBuilder.build(request)
         → CapabilityValidator.validate(profile, transport_requirements)
         → ExporterRegistry.get(format).export(data, profile)
ШАГ 3: Вернуть результат (str)
```

Все компоненты создаются в одном месте (composition root). Никакой DI-фреймворк не используется. Никакие глобальные переменные не мутируют после завершения инициализации.

---

## 6. Финальная проверка OCP

### 6.1 Сценарий 1: Добавить транспорт QUIC-X

**Новые файлы:**
- `app/services/serializers/quic_x_config.py` — `QuicXConfig` датакласс
- `app/services/serializers/quic_x_serializer.py` — `QuicXSerializer`

**Изменяемые существующие файлы:**
- `app/_bootstrap.py` — добавить строку `registry.register("quic-x", QuicXSerializer())`
- `app/_dependencies.py` — добавить импорт `QuicXSerializer` (если регистрация в `_register_default_transports`)

**Почему изменяются:**
- `_bootstrap.py` / `_dependencies.py` — это точка сборки приложения. Это "composition root". По определению, composition root изменяется при добавлении новых компонентов. Это НЕ нарушает OCP, так как composition root — это единственное место, где собираются зависимости.

**OCP-статус: СОБЛЮДЕНО** (изменяется только composition root).

### 6.2 Сценарий 2: Добавить клиент V2RayNG v7

**Новые файлы:**
- `app/capabilities/v2rayn_v7.py` — `V2RayNGV7Capability` профиль (данные, а не код)

**Изменяемые существующие файлы:**
- `app/_dependencies.py` — добавить `capability_registry.register("v2rayn-v7", V2RayNGV7Capability())`

**Почему изменяются:**
- Только composition root. Capability — это данные, не код.

**OCP-статус: СОБЛЮДЕНО.**

### 6.3 Сценарий 3: Добавить экспорт TOML

**Новые файлы:**
- `app/services/exporters/toml_exporter.py` — `TomlExporter`

**Изменяемые существующие файлы:**
- `app/_dependencies.py` — добавить `exporter_registry.register("toml", TomlExporter())`

**Почему изменяются:**
- Только composition root.

**OCP-статус: СОБЛЮДЕНО.**

### 6.4 Сценарий 4: Добавить новую Capability

**Сценарий:** Потребовалась поддержка `SUPPORTS_MULTIPLEX` (мультиплексирование соединений).

**Новые файлы:**
- (возможно) обновление `Capability` enum — но enum можно расширить без изменения существующих значений
- Файлы транспортов, которым нужна эта capability — они укажут `SUPPORTS_MULTIPLEX` в `required_capabilities()`
- Файлы клиентов, которые поддерживают эту capability — они добавят `SUPPORTS_MULTIPLEX` в свой профиль

**Изменяемые существующие файлы:**
- `app/models/capability.py` — добавить `SUPPORTS_MULTIPLEX = "supports_multiplex"` в Capability enum

**Почему изменяется:**
- Enum Capability — это точка расширения по определению. Добавление нового значения enum не нарушает OCP, так как не изменяет существующую логику, только расширяет пространство значений.

**Если потребуется добавить правило валидации:**
- `app/services/capability_validator.py` — добавить новое правило в `CAPABILITY_DEPENDENCIES`. Это также расширение, не модификация существующей логики (если валидатор использует data-driven подход с конфигурацией).

**OCP-статус: СОБЛЮДЕНО.**

---

## 7. Architecture Constraints

### 7.1 Запрещённые паттерны

После утверждения Architecture v1.0.x следующие паттерны ЗАПРЕЩЕНЫ в production-коде:

| № | Запрещённый паттерн | Обоснование | Альтернатива |
|---|---|---|---|
| 1 | `switch`/`match` по transport name | Нарушает OCP, требует изменения при добавлении транспорта | TransportRegistry.get() |
| 2 | `if`/`elif` по client name | Нарушает OCP, требует изменения при добавлении клиента | CapabilityRegistry + ExporterRegistry.get() |
| 3 | `dict[str, Any]` без формального контракта | RUNTIME-ошибки (см. BUG-001) | Типизированный TransportConfig датакласс |
| 4 | User-Agent как основной механизм выбора формата | Ненадёжно, непредсказуемо | Параметр `?format=` |
| 5 | Хранение параметров транспорта вне TransportConfig | Дублирование, несогласованность | TransportConfig с конкретными полями |
| 6 | Сериализация транспорта вне TransportSerializer | Нарушение SRP, дублирование | TransportSerializer в TransportRegistry |
| 7 | Экспорт вне Exporter | Нарушение SRP | Exporter в ExporterRegistry |
| 8 | Скрытые зависимости (глобальные переменные, неявный DI) | Непредсказуемое поведение | Явный DI через конструктор |

### 7.2 Механизм исключений

Любое отступление от Architecture Constraints должно оформляться отдельным ADR, который:

1. Описывает контекст (почему constraint не применим)
2. Описывает альтернативы (почему они не подходят)
3. Указывает срок действия исключения (если временное)
4. Указывает plan по устранению исключения (если постоянное — объяснить почему)

Исключение без ADR считается архитектурной ошибкой.

---

## 8. Backward Compatibility

### 8.1 Стратегия внедрения

Внедрение новой архитектуры выполняется в 4 фазы без остановки сервиса.

### 8.2 Компоненты: старые и новые

| Компонент | Старый (legacy) | Новый | Действие |
|---|---|---|---|
| URI-билдинг | `SingBoxClientDbService._build_vless_uri()` | `UriExporter` | Заменить |
| URI-билдинг (дубль) | `SingBoxClientService._build_vless_uri()` | `UriExporter` | Заменить |
| Inbound-парсинг | `_load_inbounds()` / `_find_inbound()` (в 3 сервисах) | `InboundParser` | Заменить |
| Валидация | `sing-box check` в dry-run | Оставить (не заменяется) | Не изменять |
| Subscription | Отсутствует | `SubscriptionBuilder` | Создать новый |
| Клиентские профили | Отсутствуют | `CapabilityRegistry` | Создать новый |
| TransportConfig | Отсутствует (dict, строки) | `TransportConfig` иерархия | Создать новый |

### 8.3 Порядок миграции

```
Фаза 1: Parallel Run (неделя 1-2)
├── Новая архитектура развёрнута рядом со старой
├── Старый _build_vless_uri() остаётся основным
├── Новый UriExporter работает параллельно, логи compare
├── SubscriptionBuilder НЕ включён в production-трафик
└── Критерий: 100% совпадение URI в параллельном прогоне

Фаза 2: Feature Parity (неделя 3-4)
├── SubscriptionBuilder включён через feature-flag
├── Трафик постепенно переключается на новый код (10% → 50% → 100%)
├── Старый _build_vless_uri() больше не вызывается
├── Legacy-код помечен @deprecated
└── Критерий: 0 регрессий за 7 дней

Фаза 3: Legacy Freeze (неделя 5)
├── Legacy _build_vless_uri() заморожен (no changes)
├── Все новые фичи — только через новую архитектуру
├── Подготовка к удалению legacy
└── Критерий: feature-flag включён для 100% трафика

Фаза 4: Legacy Removal (неделя 6)
├── Удаление SingBoxClientDbService._build_vless_uri()
├── Удаление SingBoxClientService._build_vless_uri()
├── Удаление _load_inbounds() / _find_inbound() дубликатов
├── Очистка imports
└── Критерий: код не содержит ссылок на старые методы
```

### 8.4 Критерии удаления legacy-кода

- [ ] 100% production-трафика проходит через новую архитектуру
- [ ] Feature-flag включён постоянно (не используется fallback)
- [ ] Нет ошибок, связанных с новой архитектурой, за 7 дней
- [ ] Тесты покрывают новую архитектуру
- [ ] Документация обновлена

### 8.5 Момент полного отключения старой архитектуры

Конец недели 6 при условии выполнения критериев удаления. Две архитектуры НЕ могут сосуществовать бесконечно.

---

## 9. Definition of Done

### 9.1 Чеклист PHASE-04.2.1

| № | Требование | Статус |
|---|---|---|
| 1 | Отсутствуют открытые архитектурные вопросы | ✓ |
| 2 | Описаны все Registry (ExporterRegistry, TransportRegistry, CapabilityRegistry) | ✓ |
| 3 | Описаны все контракты (Exporter, TransportSerializer) | ✓ |
| 4 | Описана Capability Validation | ✓ |
| 5 | Определён жизненный цикл компонентов (DI) | ✓ |
| 6 | Выполнена проверка OCP (4 сценария) | ✓ |
| 7 | Выполнена проверка SOLID | ✓ |
| 8 | Архитектура допускает расширение без изменения production-кода | ✓ |
| 9 | Определена стратегия миграции | ✓ |
| 10 | ADR (6 шт.) документированы | ✓ |
| 11 | Architecture Constraints определены | ✓ |
| 12 | Отчёт опубликован через ReportHub | |

### 9.2 Проверка SOLID

| Принцип | Проверка |
|---|---|
| **S**ingle Responsibility | TransportSerializer: только сериализация. Exporter: только экспорт. Registry: только регистрация/поиск. CapabilityValidator: только валидация. |
| **O**pen/Closed | Новые транспорты, клиенты, форматы — без изменения существующего production-кода (см. 6). |
| **L**iskov Substitution | Все TransportSerializer реализуют один Protocol — взаимозаменяемы. |
| **I**nterface Segregation | TransportSerializer: 2 метода. Exporter: 1 метод. Минимальные интерфейсы. |
| **D**ependency Inversion | Высокоуровневый UriExporter зависит от абстракции TransportRegistry (а не от конкретных сериализаторов). SubscriptionBuilder зависит от абстракций ExporterRegistry и CapabilityRegistry. |

---

## 10. FINAL ENGINEERING REVIEW

### 1. Можно ли начинать production-разработку?

**ДА.**

Архитектура v1.0.1 полностью описывает компоненты, контракты, жизненный цикл, правила расширения и стратегию миграции. Нет открытых архитектурных вопросов. Протокол PHASE-04.2.1 выполнен полностью.

### 2. Оценка готовности архитектуры

**98%**

Оставшиеся 2%:
- Полнота таксономии Capability будет уточнена при реализации первых 10 транспортов (возможно, потребуются новые значения)
- Версионирование моделей зарезервировано архитектурно, но не реализовано (отложено до PHASE-06)

### 3. Архитектурный риск

**LOW**

Риски и их митигация:

| Риск | Вероятность | Влияние | Митигация |
|---|---|---|---|
| Неполнота таксономии Capability | Medium | Low | Capability — это enum, расширение не меняет существующий код |
| CapabilityModel не покрывает edge case клиента | Low | Medium | Возможность создать кастомный Exporter для клиента |
| Ошибка порядка инициализации Registry | Low | High | Чёткий DI bootstrap; assertion при получении |
| Производительность Registry lookup | Low | Low | dict lookup O(1); Registry маленькие |

### 4. Что может потребовать полного переписывания через год?

**Ничего при условии соблюдения Architecture Constraints.**

Потенциальные сценарии, которые потребуют изменений (не полного переписывания):
- **Новый протокол订阅 (subscription)**: если клиенты перестанут использовать URI/JSON/YAML — потребуется новый Exporter. Архитектура это поддерживает.
- **Версионирование**: при появлении v2 схемы TransportConfig — потребуется SchemaMigrationRegistry. Архитектура это предусмотрела (п. 4).
- **Динамическая загрузка плагинов**: если потребуется подгружать транспорты из внешних модулей — Registry можно адаптировать. Это расширение, не переписывание.

Единственный сценарий полного переписывания — если отказываемся от Capability-based подхода в пользу другого архитектурного стиля. На текущий момент нет оснований для этого.

### 5. Что рекомендуется изменить до начала реализации?

**Ничего критического.**

Рекомендации (не обязательные, но желательные):
1. Согласовать полный список Capability для PHASE-04.3 (первые 3 транспорта: xHTTP, WebSocket, gRPC) до написания кода.
2. Определить точный набор первых ClientCapability (V2RayNG, sing-box, Clash) в collaboration с командой.
3. Написать тесты для CapabilityValidator до реализации экспортёров.

### 6. Рекомендация

**START IMPLEMENTATION**

---

*Конец документа Architecture v1.0.1*
