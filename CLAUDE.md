# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A-Stock Trading is an AI-powered multi-agent stock trading analysis system for the Chinese A-share market. It implements a TradingAgents-style architecture where multiple AI experts analyze stocks from different perspectives (technical, capital flow, fundamental, industry comparison, sentiment) and debate to reach consensus.

**Backend**: Python Flask on port 5001
**Frontend**: Vite + React on port 5173

## Development Commands

```bash
# Backend (from project root)
# Activate virtual environment (if needed)
source venv/Scripts/activate  # Windows
source venv/bin/activate      # Linux/Mac

# Install backend dependencies
pip install -r requirements.txt

# Run backend server
python api_server.py

# Frontend
cd stock_frontend
npm install
npm run dev          # Start dev server on port 5173
npm run build        # Build for production
npm run lint         # Run ESLint
```

## Architecture

### Backend Structure

- **`api_server.py`** - Flask entry point, registers routes and initializes database
- **`api_routes.py`** - All API endpoints (data, AI analysis, agents, debate jobs)
- **`data_fetchers.py`** - Fetches stock data from Sina and Eastmoney public APIs
- **`technical_indicators.py`** - Calculates 20+ indicators (MA, EMA, MACD, RSI, KDJ, BOLL, OBV, WR)
- **`data_formatters.py`** - Formats stock data for AI consumption
- **`ai_service.py`** - Unified interface for multiple AI providers (OpenAI, DeepSeek, Qwen, Gemini, SiliconFlow)
- **`models.py`** - SQLAlchemy models: `Watchlist`, `Config`, `Agent`, `AnalysisCache`, `DebateJob`
- **`db.py`** - Database operations wrapper
- **`init_agents.py`** - Default AI agent configurations

### Frontend Structure (`stock_frontend/src/`)

- **`pages/`** - Route pages: Home, StockDetail, AIDebate, Settings, Tasks, Watchlist, Strategy
- **`components/`** - Reusable components: AIAnalyzeButton, CandlestickChart, Layout
- **`services/api.ts`** - API client with base URL configuration
- **`store/`** - Zustand state management (config, watchlist)

### Database (SQLite at `database.db`)

- **`watchlist`** - User's favorite stocks
- **`config`** - Key-value configuration storage
- **`agents`** - AI agent definitions with prompts
- **`analysis_cache`** - Cached AI analysis results
- **`debate_jobs`** - Multi-agent debate task tracking

## Multi-Agent Debate System

The core feature is a multi-agent debate mechanism:

1. **Analysis Phase**: Each agent independently analyzes the stock (1-3 rounds)
2. **Debate Phase**: Agents read each other's analysis and debate (1-2 rounds)
3. **Decision Phase**: An "operator" agent synthesizes all inputs into a final report

Default agents: Technical Analysis, Capital Flow, Fundamental, Industry Comparison, Sentiment, Bull/Bear experts.

## Key API Patterns

- Stock codes use 6-digit format (e.g., "000001")
- All AI analysis is async via `debate_jobs` table with status tracking
- Data fetching combines multiple public APIs (Sina, Eastmoney) with no paid dependencies
- Technical indicators are calculated server-side from raw kline data

## Adding New Features

- **New data source**: Add function to `data_fetchers.py`, format in `data_formatters.py`
- **New agent**: Add to `init_agents.py` DEFAULT_AGENTS list
- **New API endpoint**: Register in `api_routes.py` `register_routes()` function
- **New frontend page**: Add to `pages/`, update routing in `App.tsx`

## Environment Variables

Backend:
- `HOST` - Server host (default: 0.0.0.0)
- `PORT` - Server port (default: 5001)
- `FLASK_DEBUG` - Debug mode (default: 0)
- `DASHSCOPE_API_BASE` - Qwen API base URL
- `SILICONFLOW_API_BASE` - SiliconFlow API base URL

AI API keys are configured via the frontend Settings page and stored in localStorage.
