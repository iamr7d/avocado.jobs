# JobMatchBot - AI-Powered Job Matching Telegram Bot

JobMatchBot is a Telegram bot that helps users find job opportunities that match their resume and preferences. It uses Groq AI to analyze resumes and provide personalized job matches with detailed scoring.

## Features

- **Resume Analysis**: Upload your resume as a PDF and get AI-powered job matches
- **Personalized Job Matching**: Set your job preferences including keywords, location, and minimum match score
- **Daily Job Alerts**: Receive daily job notifications at your preferred time
- **Detailed Match Analysis**: Each job comes with a match score and detailed analysis of strengths and potential gaps
- **Multiple Job Sources**: Jobs are scraped from LinkedIn and Indeed

## Setup

### Prerequisites

- Python 3.8+
- Telegram Bot Token (from BotFather)
- Groq API Key

### Installation

1. Clone the repository
2. Create a virtual environment: `python -m venv avenv`
3. Activate the virtual environment:
   - Windows: `avenv\Scripts\Activate.ps1`
   - Linux/Mac: `source avenv/bin/activate`
4. Install dependencies: `pip install -r requirements.txt`
5. Create a `.env` file with the following variables:
   ```
   TELEGRAM_BOT_TOKEN=your_telegram_bot_token
   GROQ_API_KEY=your_groq_api_key
   GROQ_MODEL=llama3-70b-8192
   ```
6. Run the bot: `python joy.py`

## Usage

### Bot Commands

- `/start` - Start or restart the bot
- `/preferences` - Set all preferences at once
- `/keywords [job titles]` - Set job search keywords
- `/location [place]` - Set job search location
- `/score [number]` - Set minimum match score
- `/time [HH:MM]` - Set daily notification time
- `/jobs` - Get jobs immediately
- `/pause` - Pause daily notifications
- `/resume` - Resume daily notifications
- `/status` - Check your current settings

## Job Matching Algorithm

The bot uses Groq AI to analyze the match between a user's resume and job listings. The matching algorithm:

1. Extracts text from the user's resume
2. Scrapes job listings from multiple sources
3. For each job, sends the resume and job details to Groq AI
4. Receives a match score (0-100) and detailed analysis
5. Sends jobs that meet the user's minimum match score

## Future Enhancements

- Add more job sources
- Implement resume improvement suggestions
- Add interview preparation assistance
- Create a web dashboard for more detailed analytics