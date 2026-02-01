# HealthCopilot

An AI-powered nutrition tracking system that combines meal photo recognition with personalized health insights. Log your meals via photo or text, and let GPT-4 Vision automatically extract ingredients and calculate nutritional information.

![License](https://img.shields.io/badge/license-MIT-blue.svg)
![Platform](https://img.shields.io/badge/platform-iOS%20%7C%20Web-lightgrey)
![Swift](https://img.shields.io/badge/Swift-5.9-orange)
![React](https://img.shields.io/badge/React-19-61DAFB)

## Features

- **AI Meal Recognition** - Snap a photo of your meal and GPT-4 Vision identifies ingredients with portion estimates
- **Text Logging** - Quick text-based meal entry with natural language parsing
- **USDA Nutrition Data** - Automatic macro calculation using the USDA FoodData Central database
- **Apple Health Integration** - Sync with HealthKit for comprehensive health tracking
- **Real-time Sync** - Seamless data sync between iOS app and cloud backend
- **Web Dashboard** - Review, edit, and correct meal data from any browser
- **Personalization System** - Learning from user corrections to improve accuracy over time

## Architecture

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│    iOS App      │────▶│   PocketBase     │◀────│  Web Dashboard  │
│   (SwiftUI)     │     │    (Backend)     │     │    (React)      │
└────────┬────────┘     └────────┬─────────┘     └─────────────────┘
         │                       │
         │                       ▼
         │              ┌──────────────────┐
         │              │   ML Pipeline    │
         └─────────────▶│   (Python)       │
                        │  - GPT-4 Vision  │
                        │  - USDA Lookup   │
                        └──────────────────┘
```

## Tech Stack

| Component | Technology |
|-----------|------------|
| **iOS App** | SwiftUI, HealthKit, URLSession |
| **Backend** | PocketBase (SQLite-based BaaS) |
| **Web Dashboard** | React 19, Vite, Tailwind CSS |
| **ML Pipeline** | Python, OpenAI GPT-4 Vision API |
| **Nutrition Data** | USDA FoodData Central |
| **Deployment** | Render (Docker) |

## Project Structure

```
HealthCopilot/
├── Views/                    # SwiftUI views
│   ├── HealthCopilotApp.swift
│   ├── RootView.swift
│   ├── LogView.swift
│   ├── CameraView.swift
│   └── ...
├── Managers/                 # iOS service managers
│   ├── GPTVisionService.swift
│   ├── HealthKitManager.swift
│   ├── SyncManager.swift
│   └── MealLogManager.swift
├── backend/                  # PocketBase backend
│   ├── Dockerfile
│   ├── pb_migrations/        # Database migrations
│   └── pocketbase            # PocketBase binary
├── web-dashboard/           # React web app
│   └── dashboard/
│       ├── src/
│       │   ├── Dashboard.jsx
│       │   ├── DayDetail.jsx
│       │   ├── CorrectionModal.jsx
│       │   └── ...
│       └── package.json
├── ml-pipeline/             # Python ML scripts
│   └── nutrition-pipeline/
│       ├── enrich_meals.py   # Main processing script
│       ├── parser_gpt.py     # GPT-4 Vision integration
│       ├── lookup_usda.py    # USDA nutrition lookup
│       └── pb_client.py      # PocketBase client
└── render.yaml              # Render deployment config
```

## Getting Started

### Prerequisites

- **iOS Development**: Xcode 15+, iOS 17+
- **Backend**: PocketBase binary or Docker
- **Web Dashboard**: Node.js 18+
- **ML Pipeline**: Python 3.10+

### 1. Backend Setup

```bash
cd backend

# Option A: Run PocketBase directly (macOS)
./pocketbase_mac serve

# Option B: Run with Docker
docker build -t healthcopilot-backend .
docker run -p 8090:8090 healthcopilot-backend
```

PocketBase admin UI: `http://localhost:8090/_/`

### 2. iOS App Setup

1. Open `HealthCopilot.xcodeproj` in Xcode
2. Update the PocketBase URL in `SyncManager.swift`
3. Add your OpenAI API key in `GPTVisionService.swift`
4. Build and run on your device (HealthKit requires physical device)

### 3. Web Dashboard Setup

```bash
cd web-dashboard/dashboard

# Install dependencies
npm install

# Start development server
npm run dev
```

Dashboard: `http://localhost:5173`

### 4. ML Pipeline Setup

```bash
cd ml-pipeline/nutrition-pipeline

# Create virtual environment
python -m venv venv
source venv/bin/activate  # or `venv\Scripts\activate` on Windows

# Install dependencies
pip install -r requirements.txt

# Copy and configure environment
cp .env.example .env
# Edit .env with your API keys

# Run the enrichment pipeline
python enrich_meals.py --last-week
```

## Environment Variables

### ML Pipeline (`.env`)

```bash
PB_URL=http://localhost:8090
PB_EMAIL=your-email@example.com
PB_PASSWORD=your-password
OPENAI_API_KEY=sk-your-openai-key
USDA_API_KEY=your-usda-api-key
```

Get a free USDA API key at: https://fdc.nal.usda.gov/api-key-signup.html

## Database Schema

The system uses PocketBase with the following main collections:

| Collection | Purpose |
|------------|---------|
| `users` | User accounts and authentication |
| `meals` | Meal entries (text, images, timestamps) |
| `ingredients` | Parsed ingredients with nutrition data |
| `user_preferences` | User dietary preferences and brands |
| `ingredient_corrections` | User corrections for learning |
| `brand_foods` | Brand-specific nutrition data |
| `meal_templates` | User's recurring meals |

## API Endpoints

### Meals
- `GET /api/collections/meals/records` - List all meals
- `POST /api/collections/meals/records` - Create new meal
- `PATCH /api/collections/meals/records/{id}` - Update meal

### Ingredients
- `GET /api/collections/ingredients/records` - List ingredients
- `POST /api/collections/ingredients/records` - Create ingredient

### User Preferences
- `GET /api/collections/user_preferences/records` - Get preferences
- `POST /api/collections/user_preferences/records` - Create/update preferences

## Development Roadmap

The project follows a tiered MVP approach:

- [x] **Tier 1**: Foundation - Basic personalization, meal corrections
- [ ] **Tier 2**: Learning System - Feedback loop, portion calibration
- [ ] **Tier 3**: Context Awareness - Meal patterns, smart suggestions
- [ ] **Tier 4**: Optimization - Hybrid parsing, cost optimization

See [MVP_TIER_PLAN.md](./MVP_TIER_PLAN.md) for detailed roadmap.

## Deployment

### Render (Recommended)

The project includes a `render.yaml` for one-click deployment:

1. Fork this repository
2. Connect to Render
3. Deploy using the Blueprint

### Manual Docker Deployment

```bash
cd backend
docker build -t healthcopilot .
docker run -d -p 8090:8090 -v pb_data:/pb_data healthcopilot
```

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## License

This project is licensed under the MIT License - see the [LICENSE.md](LICENSE.md) file for details.

## Acknowledgments

- [OpenAI GPT-4 Vision](https://openai.com/gpt-4) for meal image analysis
- [USDA FoodData Central](https://fdc.nal.usda.gov/) for nutrition data
- [PocketBase](https://pocketbase.io/) for the backend framework
- [Vite](https://vitejs.dev/) and [React](https://react.dev/) for the web dashboard
