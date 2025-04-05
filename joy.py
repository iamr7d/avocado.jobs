import os
import time
import json
import requests
import schedule
import fitz  # PyMuPDF for extracting text from PDFs
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from datetime import datetime
from groq import Groq
import threading
from flask import Flask, jsonify
import logging
import random

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Telegram Bot Setup
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"

# Groq AI Setup
client = Groq(api_key=os.getenv('GROQ_API_KEY'))
GROQ_MODEL = os.getenv('GROQ_MODEL', 'llama3-70b-8192')

# Database file for user data
USER_DB_FILE = "users_data.json"

# Initialize Flask for health checks
app = Flask(__name__)

class JobSearchBot:
    def __init__(self):
        self.users = self.load_users()
        self.last_update_id = None
        
    def load_users(self):
        """Load user data from JSON file"""
        try:
            if os.path.exists(USER_DB_FILE):
                with open(USER_DB_FILE, 'r') as f:
                    return json.load(f)
            return {}
        except Exception as e:
            logger.error(f"Error loading user data: {e}")
            return {}
            
    def save_users(self):
        """Save user data to JSON file"""
        try:
            with open(USER_DB_FILE, 'w') as f:
                json.dump(self.users, f)
        except Exception as e:
            logger.error(f"Error saving user data: {e}")
            
    def register_user(self, chat_id):
        """Register a new user if not already registered
        Returns True if this is a new user, False if user already exists"""
        chat_id_str = str(chat_id)
        if chat_id_str not in self.users:
            self.users[chat_id_str] = {
                "resume": "",
                "search_keywords": ["AI Engineer"],
                "search_location": "India",
                "min_match_score": 70,
                "jobs_sent": [],
                "notification_time": "09:00",
                "is_active": True,
                "last_activity": datetime.now().isoformat(),
                "welcomed": True  # Mark that welcome message has been sent
            }
            self.save_users()
            return True
        return False
            
    def set_resume(self, chat_id, resume_text):
        """Store resume text for a user"""
        chat_id_str = str(chat_id)
        if chat_id_str in self.users:
            self.users[chat_id_str]["resume"] = resume_text
            self.users[chat_id_str]["last_activity"] = datetime.now().isoformat()
            self.save_users()
            return True
        return False
            
    def set_search_preferences(self, chat_id, keywords=None, location=None, min_score=None, notification_time=None):
        """Update user search preferences"""
        chat_id_str = str(chat_id)
        if chat_id_str in self.users:
            if keywords is not None:
                self.users[chat_id_str]["search_keywords"] = keywords
            if location is not None:
                self.users[chat_id_str]["search_location"] = location
            if min_score is not None:
                self.users[chat_id_str]["min_match_score"] = min_score
            if notification_time is not None:
                self.users[chat_id_str]["notification_time"] = notification_time
            self.users[chat_id_str]["last_activity"] = datetime.now().isoformat()
            self.save_users()
            return True
        return False
    
    def extract_text_from_pdf(self, pdf_path):
        """Extract text from a PDF file"""
        try:
            doc = fitz.open(pdf_path)
            text = "\n".join([page.get_text("text") for page in doc])
            return text.strip() if text else "❌ Unable to extract text."
        except Exception as e:
            logger.error(f"PDF extraction error: {e}")
            return "❌ Error reading PDF."
            
    def handle_document(self, file_id, chat_id):
        """Download PDF from Telegram and process it"""
        try:
            file_info = requests.get(f"{TELEGRAM_URL}/getFile?file_id={file_id}").json()
            if "result" in file_info:
                file_path = file_info["result"]["file_path"]
                file_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_path}"
                response = requests.get(file_url)
                
                if response.status_code == 200:
                    os.makedirs("resumes", exist_ok=True)
                    pdf_path = f"resumes/resume_{chat_id}.pdf"
                    with open(pdf_path, "wb") as f:
                        f.write(response.content)
                        
                    resume_text = self.extract_text_from_pdf(pdf_path)
                    if self.set_resume(chat_id, resume_text):
                        self.send_message(chat_id, "✅ Resume received! I'll start sending job matches based on your profile.")
                        
                        # Now ask for user preferences
                        self.ask_for_preferences(chat_id)
                    else:
                        self.send_message(chat_id, "❌ Failed to save your resume. Please try again.")
                else:
                    self.send_message(chat_id, "❌ Failed to download the PDF.")
        except Exception as e:
            logger.error(f"Error handling document: {e}")
            self.send_message(chat_id, "❌ Something went wrong processing your document.")
            
    def ask_for_preferences(self, chat_id):
        """Ask user for job search preferences"""
        message = (
            "🔍 Let's customize your job search!\n\n"
            "Please send your preferences in this format:\n"
            "/preferences [job titles] | [location] | [minimum match %] | [notification time]\n\n"
            "Example: /preferences Data Scientist, ML Engineer | New York | 75 | 08:00\n\n"
            "Or you can set them individually:\n"
            "/keywords Data Scientist, ML Engineer\n"
            "/location New York\n"
            "/score 75\n"
            "/time 08:00"
        )
        self.send_message(chat_id, message)
            
    def ask_for_resume(self, chat_id):
        """Send a message asking for resume"""
        message = "🚀 Please send your resume (as a PDF) so I can match jobs for you!"
        self.send_message(chat_id, message)
    
    def send_message(self, chat_id, text, parse_mode=None):
        """Send message to user"""
        data = {"chat_id": chat_id, "text": text}
        if parse_mode:
            data["parse_mode"] = parse_mode
        try:
            response = requests.post(f"{TELEGRAM_URL}/sendMessage", data=data)
            if response.status_code != 200:
                logger.error(f"Failed to send message: {response.text}")
        except Exception as e:
            logger.error(f"Error sending message: {e}")
            
    def get_match_score(self, job_data, resume_text):
        """AI-powered job matching score with detailed analysis"""
        prompt = f"""
        Resume:
        {resume_text[:2000]}...  # Truncate to avoid token limits
        
        Job Details:
        Title: {job_data['title']}
        Company: {job_data['company']}
        Location: {job_data['location']}
        
        Task: Evaluate how well this candidate's profile matches the job.
        
        Please provide:
        1. A numerical match score (0-100)
        2. 3-5 key strengths that make this candidate suitable
        3. 1-2 potential gaps in the candidate's profile
        4. 2-3 specific suggestions to improve candidacy for this role
        
        Format your response as:
        Score: [number]
        Strengths: [bullet points]
        Gaps: [bullet points]
        Suggestions: [bullet points]
        """
        
    def get_resume_improvement_suggestions(self, resume_text, job_keywords):
        """Get AI-powered resume improvement suggestions based on job keywords"""
        prompt = f"""
        Resume:
        {resume_text[:3000]}...  # Truncate to avoid token limits
        
        Job Keywords: {', '.join(job_keywords)}
        
        Task: Provide specific suggestions to improve this resume for jobs related to the keywords.
        
        Please provide:
        1. 3-5 specific improvements to make the resume more effective
        2. 2-3 skills or experiences that should be highlighted more prominently
        3. Any formatting or structure suggestions
        
        Format your response as:
        Improvements:
        - [improvement 1]
        - [improvement 2]...
        
        Skills to Highlight:
        - [skill 1]
        - [skill 2]...
        
        Formatting Suggestions:
        - [suggestion 1]
        - [suggestion 2]...
        """
        
        try:
            response = client.chat.completions.create(
                messages=[{"role": "user", "content": prompt}],
                model=GROQ_MODEL,
                temperature=0.3
            )
            
            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"Resume improvement error: {e}")
            return "Error generating resume improvement suggestions."
            
    def send_resume_analysis(self, chat_id):
        """Send detailed resume analysis"""
        chat_id_str = str(chat_id)
        
        if chat_id_str not in self.users:
            return
            
        user_data = self.users[chat_id_str]
        
        if not user_data["resume"]:
            self.ask_for_resume(chat_id)
            return
            
        self.send_message(chat_id, "🔍 Analyzing your resume... This may take a minute.")
        
        # Get resume improvement suggestions
        suggestions = self.get_resume_improvement_suggestions(
            user_data["resume"], 
            user_data["search_keywords"]
        )
        
        message = (
            "📋 *Resume Analysis*\n\n"
            f"{suggestions}\n\n"
            "Would you like me to help you implement these suggestions? Reply with /improve to get started."
        )
        
        self.send_message(chat_id, message, parse_mode="Markdown")
        
        try:
            response = client.chat.completions.create(
                messages=[{"role": "user", "content": prompt}],
                model=GROQ_MODEL,
                temperature=0.2
            )
            
            result = response.choices[0].message.content
            
            # Extract score from AI response
            if "Score:" in result:
                score_line = [line for line in result.split('\n') if "Score:" in line][0]
                score = int(''.join(filter(str.isdigit, score_line)))
                return {"score": min(max(score, 0), 100), "analysis": result}
            else:
                # Fallback if format is unexpected
                return {"score": 50, "analysis": result}
        except Exception as e:
            logger.error(f"Scoring error: {e}")
            return {"score": 50, "analysis": "Error in analysis"}
            
    def scrape_jobs(self, keywords, location):
        """Scrape jobs from multiple sources"""
        job_list = []
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
        
        # Random delay to avoid being blocked
        time.sleep(random.uniform(1, 3))
        
        # LinkedIn Scraper
        try:
            keywords_str = '+'.join(keywords[0].replace(',', ' ').split())
            linkedin_url = f"https://www.linkedin.com/jobs/search/?keywords={keywords_str}&location={location}"
            response = requests.get(linkedin_url, headers=headers)
            
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, 'html.parser')
                
                for job in soup.select('.base-card')[:10]:
                    try:
                        job_list.append({
                            "source": "LinkedIn",
                            "title": job.select_one('h3').text.strip(),
                            "company": job.select_one('h4').text.strip(),
                            "location": job.select_one('.job-search-card__location').text.strip(),
                            "link": job.select_one('a')['href'],
                            "id": f"li_{hash(job.select_one('a')['href'])}"
                        })
                    except Exception as e:
                        logger.error(f"LinkedIn parsing error: {e}")
        except Exception as e:
            logger.error(f"LinkedIn scraping error: {e}")
        
        # Indeed Scraper
        try:
            keywords_str = '+'.join(keywords[0].replace(',', ' ').split())
            indeed_url = f"https://in.indeed.com/jobs?q={keywords_str}&l={location.replace(' ', '+')}"
            response = requests.get(indeed_url, headers=headers)
            
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, 'html.parser')
                
                for job in soup.select('.job_seen_beacon')[:10]:
                    try:
                        job_id = f"indeed_{hash(job.select_one('h2 a')['href'])}"
                        job_list.append({
                            "source": "Indeed",
                            "title": job.select_one('h2 a').text.strip(),
                            "company": job.select_one('.companyName').text.strip(),
                            "location": job.select_one('.companyLocation').text.strip(),
                            "link": 'https://in.indeed.com' + job.select_one('h2 a')['href'],
                            "id": job_id
                        })
                    except Exception as e:
                        logger.error(f"Indeed parsing error: {e}")
        except Exception as e:
            logger.error(f"Indeed scraping error: {e}")
            
        return job_list
        
    def send_jobs_to_user(self, chat_id):
        """Send matching jobs to a specific user"""
        chat_id_str = str(chat_id)
        
        if chat_id_str not in self.users or not self.users[chat_id_str]["is_active"]:
            return
            
        user_data = self.users[chat_id_str]
        
        if not user_data["resume"]:
            self.ask_for_resume(chat_id)
            return
            
        # Get jobs
        jobs = self.scrape_jobs(user_data["search_keywords"], user_data["search_location"])
        
        if not jobs:
            self.send_message(chat_id, "🔍 No new job matches found today. I'll keep searching!")
            return
            
        # Filter out already sent jobs
        new_jobs = [job for job in jobs if job["id"] not in user_data["jobs_sent"]]
        
        if not new_jobs:
            self.send_message(chat_id, "🔍 No new job matches found today. I'll keep searching!")
            return
            
        matches_found = 0
        
        for job in new_jobs:
            # Add to sent list immediately to avoid duplicates
            user_data["jobs_sent"].append(job["id"])
            if len(user_data["jobs_sent"]) > 100:  # Keep list manageable
                user_data["jobs_sent"] = user_data["jobs_sent"][-100:]
                
            # Get match score
            match_result = self.get_match_score(job, user_data["resume"])
            score = match_result["score"]
            analysis = match_result["analysis"]
            
            # Only send if above threshold
            if score >= user_data["min_match_score"]:
                matches_found += 1
                
                message = (
                    f"🚀 *New Job Match!*\n\n"
                    f"📌 *{job['title']}*\n"
                    f"🏢 {job['company']}\n"
                    f"📍 {job['location']}\n"
                    f"🌐 Source: {job['source']}\n"
                    f"📊 *AI Match Score:* {score}%\n\n"
                    f"*Analysis:*\n{analysis}\n\n"
                    f"🔗 [Apply Here]({job['link']})"
                )
                
                self.send_message(chat_id, message, parse_mode="Markdown")
                
                # Avoid Telegram rate limits
                time.sleep(1)
                
        if matches_found == 0:
            self.send_message(chat_id, f"🔍 I found {len(new_jobs)} new jobs, but none met your minimum match score of {user_data['min_match_score']}%. I'll keep searching!")
        else:
            self.send_message(chat_id, f"✅ Sent you {matches_found} job matches today! I'll send more when I find them.")
            
        # Save updated jobs sent
        self.save_users()
        
    def send_jobs_to_all_users(self):
        """Send jobs to all active users"""
        logger.info("Starting daily job alerts for all users")
        for chat_id, user_data in self.users.items():
            if user_data["is_active"]:
                try:
                    # Start each user's job search in a separate thread
                    threading.Thread(target=self.send_jobs_to_user, args=(chat_id,)).start()
                    # Slight delay to avoid overwhelming the system
                    time.sleep(2)
                except Exception as e:
                    logger.error(f"Error sending jobs to user {chat_id}: {e}")
                    
    def parse_command(self, text, chat_id, skip_welcome=False):
        """Parse and handle user commands"""
        text = text.strip()
        
        if text.startswith("/start"):
            is_new_user = self.register_user(chat_id)
            if not skip_welcome and (is_new_user or text == "/start"):
                welcome_msg = (
                    "👋 Welcome to JobMatchBot!\n\n"
                    "I'll help you find jobs that match your profile. To get started:\n"
                    "1️⃣ Send me your resume as a PDF file\n"
                    "2️⃣ I'll ask you for job search preferences\n"
                    "3️⃣ I'll send you daily job matches with AI-powered match scores\n\n"
                    "Type /help anytime to see available commands."
                )
                self.send_message(chat_id, welcome_msg)
                self.ask_for_resume(chat_id)
            
        elif text.startswith("/help"):
            help_msg = (
                "🤖 *JobMatchBot Commands* 🤖\n\n"
                "/start - Start or restart the bot\n"
                "/preferences - Set all preferences at once\n"
                "/keywords [job titles] - Set job search keywords\n"
                "/location [place] - Set job search location\n"
                "/score [number] - Set minimum match score\n"
                "/time [HH:MM] - Set daily notification time\n"
                "/jobs - Get jobs immediately\n"
                "/analyze - Get resume analysis and improvement suggestions\n"
                "/pause - Pause daily notifications\n"
                "/resume - Resume daily notifications\n"
                "/status - Check your current settings"
            )
            self.send_message(chat_id, help_msg, parse_mode="Markdown")
            
        elif text.startswith("/preferences"):
            try:
                # Format: /preferences [keywords] | [location] | [score] | [time]
                parts = text.replace("/preferences", "").strip().split("|")
                if len(parts) >= 4:
                    keywords = [k.strip() for k in parts[0].split(",")]
                    location = parts[1].strip()
                    min_score = int(parts[2].strip())
                    notif_time = parts[3].strip()
                    
                    self.set_search_preferences(chat_id, keywords, location, min_score, notif_time)
                    self.send_message(chat_id, "✅ Your job search preferences have been updated!")
                else:
                    self.ask_for_preferences(chat_id)
            except Exception as e:
                logger.error(f"Error parsing preferences: {e}")
                self.send_message(chat_id, "❌ Invalid format. Please use: /preferences [keywords] | [location] | [score] | [time]")
                
        elif text.startswith("/keywords"):
            try:
                keywords = [k.strip() for k in text.replace("/keywords", "").strip().split(",")]
                if keywords and keywords[0]:
                    self.set_search_preferences(chat_id, keywords=keywords)
                    self.send_message(chat_id, f"✅ Job search keywords updated to: {', '.join(keywords)}")
                else:
                    self.send_message(chat_id, "❌ Please provide at least one keyword.")
            except Exception as e:
                logger.error(f"Error setting keywords: {e}")
                self.send_message(chat_id, "❌ Failed to update keywords. Please try again.")
                
        elif text.startswith("/location"):
            location = text.replace("/location", "").strip()
            if location:
                self.set_search_preferences(chat_id, location=location)
                self.send_message(chat_id, f"✅ Job search location updated to: {location}")
            else:
                self.send_message(chat_id, "❌ Please provide a location.")
                
        elif text.startswith("/score"):
            try:
                score = int(text.replace("/score", "").strip())
                if 0 <= score <= 100:
                    self.set_search_preferences(chat_id, min_score=score)
                    self.send_message(chat_id, f"✅ Minimum match score updated to: {score}%")
                else:
                    self.send_message(chat_id, "❌ Score must be between 0 and 100.")
            except:
                self.send_message(chat_id, "❌ Please enter a valid number.")
                
        elif text.startswith("/time"):
            time_str = text.replace("/time", "").strip()
            if time_str and len(time_str) == 5 and ":" in time_str:
                self.set_search_preferences(chat_id, notification_time=time_str)
                self.send_message(chat_id, f"✅ Daily notification time updated to: {time_str}")
            else:
                self.send_message(chat_id, "❌ Please enter time in HH:MM format.")
                
        elif text.startswith("/jobs"):
            self.send_message(chat_id, "🔍 Searching for jobs matching your profile... This may take a minute.")
            threading.Thread(target=self.send_jobs_to_user, args=(chat_id,)).start()
            
        elif text.startswith("/analyze"):
            self.send_message(chat_id, "📋 Analyzing your resume... This may take a minute.")
            threading.Thread(target=self.send_resume_analysis, args=(chat_id,)).start()
            
        elif text.startswith("/pause"):
            chat_id_str = str(chat_id)
            if chat_id_str in self.users:
                self.users[chat_id_str]["is_active"] = False
                self.save_users()
                self.send_message(chat_id, "⏸️ Job notifications paused. Type /resume to restart.")
                
        elif text.startswith("/resume"):
            chat_id_str = str(chat_id)
            if chat_id_str in self.users:
                self.users[chat_id_str]["is_active"] = True
                self.save_users()
                self.send_message(chat_id, "▶️ Job notifications resumed!")
                
        elif text.startswith("/extract"):
            chat_id_str = str(chat_id)
            if chat_id_str in self.users and self.users[chat_id_str]["resume"]:
                self.send_message
                
    def process_telegram_updates(self):
        """Check for new Telegram messages and handle them"""
        updates_url = f"{TELEGRAM_URL}/getUpdates"
        if self.last_update_id:
            updates_url += f"?offset={self.last_update_id + 1}"
            
        try:
            response = requests.get(updates_url, timeout=30)
            updates = response.json()
            
            if "result" in updates and updates["result"]:
                # Process all updates and update the last_update_id to the highest one
                # This ensures we don't process the same update multiple times
                updates_to_process = updates["result"]
                if updates_to_process:
                    # Update the last_update_id to the highest one before processing
                    self.last_update_id = max(update["update_id"] for update in updates_to_process)
                    
                    for update in updates_to_process:
                        if "message" in update:
                            message = update["message"]
                            chat_id = message["chat"]["id"]
                            chat_id_str = str(chat_id)
                            
                            # Register user if new and track if welcome message was sent
                            is_new_user = self.register_user(chat_id)
                            
                            if "document" in message:
                                file_id = message["document"]["file_id"]
                                self.handle_document(file_id, chat_id)
                            elif "text" in message:
                                text = message["text"]
                                # Only send welcome message for /start command
                                # and avoid duplicate welcome messages
                                if text.startswith("/start") and not is_new_user:
                                    # User already exists, just process the command without sending welcome again
                                    self.parse_command(text, chat_id, skip_welcome=True)
                                else:
                                    self.parse_command(text, chat_id)
                            
        except Exception as e:
            logger.error(f"Error processing updates: {e}")
            # Don't update last_update_id on error to retry processing
            
    def schedule_user_jobs(self):
        """Schedule job alerts for all users at their preferred times"""
        # Clear existing jobs
        schedule.clear()
        
        # Add health check job
        schedule.every(15).minutes.do(self.health_check)
        
        # Group users by notification time
        time_groups = {}
        for chat_id, user in self.users.items():
            if user["is_active"]:
                notif_time = user["notification_time"]
                if notif_time not in time_groups:
                    time_groups[notif_time] = []
                time_groups[notif_time].append(chat_id)
                
        # Schedule jobs for each time group
        for notif_time, users in time_groups.items():
            logger.info(f"Scheduling jobs at {notif_time} for {len(users)} users")
            schedule.every().day.at(notif_time).do(self.send_jobs_to_all_users)
            
        # Add a job to reschedule daily (to pick up new users/times)
        schedule.every().day.at("00:01").do(self.schedule_user_jobs)
        
    def health_check(self):
        """Health check endpoint for Railway monitoring"""
        logger.info("Health check ping")
        return "OK"
        
    def run(self):
        """Run the bot"""
        logger.info("Starting JobMatchBot...")
        
        # Schedule initial jobs
        self.schedule_user_jobs()
        
        # Start Flask app in a separate thread for health checks
        def start_flask():
            app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
            
        @app.route("/health")
        def health():
            return jsonify({"status": "ok", "users": len(self.users)})
            
        threading.Thread(target=start_flask, daemon=True).start()
        
        # Main bot loop
        while True:
            try:
                # Process Telegram updates
                self.process_telegram_updates()
                
                # Run scheduled jobs
                schedule.run_pending()
                
                # Sleep to avoid high CPU usage
                time.sleep(1)
            except Exception as e:
                logger.error(f"Error in main loop: {e}")
                time.sleep(5)  # Wait a bit longer on error
                
# Entry point
if __name__ == "__main__":
    bot = JobSearchBot()
    bot.run()