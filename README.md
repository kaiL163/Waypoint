# Waypoint

Диспетчерская панель для планирования маршрутов инженеров. Репозиторий разделён на две части:

- `backend/` — API на **Python + FastAPI** (планировщик, демо-данные, загрузка JSON/CSV)
- `frontend/` — UI на **React + Vite** (карта, диспетчерская панель)

Без запущенного backend фронтенд работать не будет.

## Требования

- Python 3.11+
- Node.js 20+ (или совместимый LTS)

## Запуск backend

```bash
cd backend
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

API будет доступен на [http://localhost:8000](http://localhost:8000). Документация: [http://localhost:8000/docs](http://localhost:8000/docs).

## Запуск frontend

В отдельном терминале:

```bash
cd frontend
npm install
```

Создайте файл `frontend/.env.local` (можно скопировать из `.env.example`):

```env
VITE_API_BASE_URL=http://localhost:8000
```

Затем:

```bash
npm run dev
```

Откройте адрес, который покажет Vite (обычно [http://localhost:5173](http://localhost:5173)).

Production-сборка фронтенда: `npm run build`.

## Быстрый сценарий

1. Запустите backend и frontend.
2. В UI нажмите «Демо-данные» → выберите сценарий (или «Использовать демо-данные»).
3. Нажмите «Построить план».
4. На карте появятся маршруты и точки заявок; под картой — сводка «кто / куда / во сколько».

Примеры файлов для загрузки: `backend/samples/demo-standard.json`, `backend/samples/demo-standard.csv` (также доступны из пустого экрана UI как «Пример JSON/CSV»).

## API

| Метод | Путь | Назначение |
|-------|------|------------|
| `GET` | `/api/health` | Проверка живости |
| `GET` | `/api/engineers` | Текущие инженеры |
| `GET` | `/api/requests` | Текущие заявки |
| `GET` | `/api/planning/current` | Текущий план |
| `POST` | `/api/planning/optimize?strategy=optimized\|baseline` | Построить план (`Dataset` в теле) |
| `POST` | `/api/planning/replan` | Событие + перепланирование |
| `GET` | `/api/data/demos` | Список демо-сценариев |
| `POST` | `/api/data/demo?scenario=standard` | Загрузить демо (`Dataset`) |
| `POST` | `/api/data/upload` | Загрузка JSON/CSV (`multipart`, поле `files`) |

Формат данных: `Dataset` / `Plan` — см. `frontend/src/model.ts` и `backend/app/models.py`.

Планировщик учитывает навык, транспорт, смену, временное окно и примерное время поездки. Пробег считается по прямому расстоянию с коэффициентом 1,3; линии на карте показывают порядок остановок, а не автомобильные дороги.

## Загрузка файлов

Поддерживаются JSON вида `{ "engineers": [...], "requests": [...] }` и CSV.

Для CSV можно:

- выбрать два файла с `engineer` / `request` (или `инженер` / `заявк`) в имени;
- либо использовать столбец `entity` со значениями `engineer` / `request`.

Координаты — WGS84 (`lat`, `lng`), время — `HH:mm`, навыки инженера в CSV разделяются `;` или `|`.

### CSV Билайн (из папки «Датасет»)

Файлы вида «Синтетические данные» / «Контрольное распределение» поддерживаются без колонок координат:

- координаты оцениваются по **району** и адресу;
- инженеры берутся из колонки **«Бригада»** (если есть) или создаются автоматически;
- длительность и навык — по **«Тип заявки HD»**.
