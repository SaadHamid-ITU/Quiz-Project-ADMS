from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from pymongo import MongoClient
import random
from functools import wraps
from datetime import datetime
import os
import PyPDF2
import google.generativeai as genai
import json

app = Flask(__name__)
app.secret_key = "quiz_secret_key_2024"
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# ============ CONFIGURE GEMINI AI ============
GEMINI_API_KEY = "AIzaSyBZWXvfWm3H6TQqz1QYN78iJJCJ9AdKeLQ"
genai.configure(api_key=GEMINI_API_KEY)

client = MongoClient("mongodb://localhost:27017/")
db = client["quizdb"]

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get("role") != "admin":
            return "Access Denied", 403
        return f(*args, **kwargs)
    return decorated_function

# ============ PDF TO QUIZ FUNCTION ============

def extract_text_from_pdf(file_path):
    text = ""
    try:
        with open(file_path, 'rb') as file:
            pdf_reader = PyPDF2.PdfReader(file)
            for page in pdf_reader.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
    except Exception as e:
        print(f"PDF extraction error: {e}")
    return text[:5000]

def generate_quiz_from_text(text, num_questions=10):
    try:
        model = genai.GenerativeModel('gemini-2.0-flash-exp')
        prompt = f"""
        You are an expert quiz generator. Based on the following content, create {num_questions} multiple choice questions.

        CONTENT:
        {text}

        INSTRUCTIONS:
        1. Create {num_questions} MCQs based ONLY on the content above
        2. Each question must have 4 options
        3. Mark the correct option (1, 2, 3, or 4)
        4. Add difficulty: "Easy", "Medium", or "Hard"
        5. Return ONLY valid JSON array, no other text

        FORMAT EXAMPLE:
        [
            {{
                "question": "What is the main topic discussed?",
                "options": ["Option A", "Option B", "Option C", "Option D"],
                "correct": 1,
                "difficulty": "Easy"
            }}
        ]

        Generate {num_questions} questions now:
        """
        response = model.generate_content(prompt)
        clean_response = response.text.strip()
        if clean_response.startswith('```json'):
            clean_response = clean_response[7:]
        elif clean_response.startswith('```'):
            clean_response = clean_response[3:]
        if clean_response.endswith('```'):
            clean_response = clean_response[:-3]
        questions = json.loads(clean_response)
        return questions
    except Exception as e:
        print(f"AI Generation Error: {e}")
        return []

# ============ API ROUTES ============

@app.route("/api/upload-pdf", methods=["POST"])
@admin_required
def upload_pdf_to_quiz():
    if 'file' not in request.files:
        return jsonify({"error": "No file uploaded"}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "No file selected"}), 400
    
    if not file.filename.endswith('.pdf'):
        return jsonify({"error": "Only PDF files are allowed"}), 400
    
    num_questions = int(request.form.get('num_questions', 10))
    
    try:
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], file.filename)
        file.save(filepath)
        text = extract_text_from_pdf(filepath)
        if not text:
            return jsonify({"error": "Could not extract text from PDF"}), 400
        questions = generate_quiz_from_text(text, num_questions)
        if not questions:
            return jsonify({"error": "Failed to generate questions"}), 500
        saved_count = 0
        for q in questions:
            q["quiz_id"] = 1
            q["created_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            db.questions.insert_one(q)
            saved_count += 1
        os.remove(filepath)
        return jsonify({
            "success": True,
            "message": f"Successfully generated {saved_count} questions from PDF",
            "questions": questions,
            "count": saved_count
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/generate-from-topic", methods=["POST"])
@admin_required
def generate_from_topic():
    data = request.get_json()
    topic = data.get('topic')
    num_questions = data.get('num_questions', 10)
    if not topic:
        return jsonify({"error": "Topic is required"}), 400
    try:
        model = genai.GenerativeModel('gemini-2.0-flash-exp')
        prompt = f"""Create {num_questions} multiple choice questions about "{topic}". Format as JSON array with fields: question, options (array of 4), correct (1-4), difficulty (Easy/Medium/Hard). Return ONLY valid JSON array."""
        response = model.generate_content(prompt)
        clean_response = response.text.strip()
        if clean_response.startswith('```json'):
            clean_response = clean_response[7:]
        if clean_response.startswith('```'):
            clean_response = clean_response[3:]
        if clean_response.endswith('```'):
            clean_response = clean_response[:-3]
        questions = json.loads(clean_response)
        saved_count = 0
        for q in questions:
            q["quiz_id"] = 1
            q["created_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            db.questions.insert_one(q)
            saved_count += 1
        return jsonify({
            "success": True,
            "message": f"Generated {saved_count} questions about '{topic}'",
            "questions": questions,
            "count": saved_count
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/get-questions", methods=["GET"])
def get_questions():
    questions = list(db.questions.find({}, {"_id": 0}))
    return jsonify({"questions": questions, "count": len(questions)})

@app.route("/api/get-results", methods=["GET"])
@admin_required
def get_results():
    results = list(db.results.find({}, {"_id": 0}))
    return jsonify({"results": results, "count": len(results)})

# ============ WEB ROUTES ============

@app.route("/")
def home():
    return redirect(url_for("login"))

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form["name"]
        email = request.form["email"]
        password = request.form["password"]
        if db.users.find_one({"email": email}):
            return "Email already exists!"
        db.users.insert_one({
            "name": name,
            "email": email,
            "password": password,
            "role": "student"
        })
        return redirect(url_for("login"))
    return render_template("register.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]
        user = db.users.find_one({"email": email, "password": password})
        if user:
            session["user_id"] = str(user["_id"])
            session["user_name"] = user["name"]
            session["user_email"] = user["email"]
            session["role"] = user.get("role", "student")
            if session["role"] == "admin":
                return redirect(url_for("admin_dashboard"))
            else:
                return redirect(url_for("student_dashboard"))
        return "Invalid credentials!"
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.route("/student_dashboard")
@login_required
def student_dashboard():
    if session["role"] == "admin":
        return redirect(url_for("admin_dashboard"))
    return render_template("student_dashboard_enhanced.html", name=session["user_name"])

# ============ QUIZ ROUTES - FIXED ============

@app.route("/quiz")
@login_required
def quiz():
    difficulty = request.args.get('difficulty', 'all')
    
    query = {"quiz_id": 1}
    if difficulty != 'all':
        query["difficulty"] = difficulty
    
    all_questions = list(db.questions.find(query))
    
    if len(all_questions) == 0:
        return "No questions found! Please add questions as admin."
    
    if len(all_questions) > 20:
        selected_questions = random.sample(all_questions, 20)
    else:
        selected_questions = all_questions
    
    # Store correct answers in session (original 1-indexed values)
    correct_answers_list = []
    difficulties_list = []
    
    for q in selected_questions:
        # Shuffle options
        options_with_index = list(enumerate(q["options"], 1))
        random.shuffle(options_with_index)
        q["shuffled_options"] = options_with_index
        
        # Find the shuffled position of the correct answer
        correct_option_text = q["options"][q["correct"] - 1]
        shuffled_correct = None
        for idx, opt in options_with_index:
            if opt == correct_option_text:
                shuffled_correct = idx
                break
        q["correct_mapping"] = shuffled_correct
        correct_answers_list.append(shuffled_correct)
        difficulties_list.append(q.get("difficulty", "Medium"))
    
    # Store in session (CRITICAL: Must be before rendering)
    session["correct_answers"] = correct_answers_list
    session["difficulties"] = difficulties_list
    session["quiz_total"] = len(selected_questions)
    
    print(f"\n=== QUIZ STARTED ===")
    print(f"Session ID: {session.get('user_id')}")
    print(f"Total questions: {session['quiz_total']}")
    print(f"Correct answers stored: {session['correct_answers']}")
    
    return render_template("quiz_enhanced.html", questions=selected_questions, difficulty=difficulty)

@app.route("/submit", methods=["POST"])
@login_required
def submit():
    # Get data from session
    correct_answers = session.get("correct_answers", [])
    difficulties = session.get("difficulties", [])
    total = len(correct_answers)
    
    print(f"\n=== SUBMIT RECEIVED ===")
    print(f"Session ID: {session.get('user_id')}")
    print(f"Session correct_answers: {correct_answers}")
    print(f"Session difficulties: {difficulties}")
    print(f"Total questions expected: {total}")
    print(f"Form data received: {dict(request.form)}")
    
    score = 0
    weighted_score = 0
    max_weighted = 0
    weight_map = {"Easy": 1, "Medium": 2, "Hard": 3}
    
    # Calculate score from form data
    for key, value in request.form.items():
        if key.startswith('answer_'):
            # Extract question index
            q_index = int(key.split('_')[1])
            
            if q_index < len(correct_answers):
                user_answer = int(value)
                correct = correct_answers[q_index]
                difficulty = difficulties[q_index] if q_index < len(difficulties) else "Medium"
                weight = weight_map.get(difficulty, 2)
                max_weighted += weight
                
                print(f"Q{q_index+1}: Correct={correct}, User={user_answer}, Difficulty={difficulty}")
                
                if user_answer == correct:
                    score += 1
                    weighted_score += weight
                    print(f"  ✓ CORRECT! Score: {score}")
                else:
                    print(f"  ✗ WRONG! Score: {score}")
    
    if total > 0:
        percentage = (score / total) * 100
    else:
        percentage = 0
    
    if max_weighted > 0:
        weighted_percentage = (weighted_score / max_weighted) * 100
    else:
        weighted_percentage = 0
    
    print(f"\n=== FINAL SCORE ===")
    print(f"Score: {score}/{total} ({percentage:.1f}%)")
    print(f"Weighted: {weighted_score}/{max_weighted} ({weighted_percentage:.1f}%)")
    
    # Save result to database
    db.results.insert_one({
        "user_email": session["user_email"],
        "user_name": session["user_name"],
        "score": score,
        "total": total,
        "percentage": percentage,
        "weighted_score": weighted_score,
        "weighted_percentage": weighted_percentage,
        "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "difficulties": difficulties
    })
    
    # Clear session data
    session.pop("correct_answers", None)
    session.pop("difficulties", None)
    session.pop("quiz_total", None)
    
    return render_template("result_enhanced.html", 
                         score=score, 
                         total=total, 
                         percentage=percentage,
                         weighted_percentage=weighted_percentage)

@app.route("/leaderboard")
def leaderboard():
    results = list(db.results.find().sort("score", -1).limit(10))
    return render_template("leaderboard_enhanced.html", results=results)

@app.route("/quiz-history")
@login_required
def quiz_history():
    results = list(db.results.find({"user_email": session["user_email"]}).sort("date", -1))
    return render_template("quiz_history.html", results=results)

@app.route("/student/analytics")
@login_required
def student_analytics():
    results = list(db.results.find({"user_email": session["user_email"]}).sort("date", -1))
    total_quizzes = len(results)
    if total_quizzes > 0:
        avg_score = sum(r["score"] for r in results) / total_quizzes
        best_score = max(r["score"] for r in results)
    else:
        avg_score = 0
        best_score = 0
    return render_template("student_analytics.html",
                         total_quizzes=total_quizzes,
                         avg_score=round(avg_score, 1),
                         best_score=best_score,
                         quiz_history=results)

@app.route("/admin_dashboard")
@admin_required
def admin_dashboard():
    total_questions = db.questions.count_documents({})
    total_students = db.users.count_documents({"role": "student"})
    total_attempts = db.results.count_documents({})
    easy_count = db.questions.count_documents({"difficulty": "Easy"})
    medium_count = db.questions.count_documents({"difficulty": "Medium"})
    hard_count = db.questions.count_documents({"difficulty": "Hard"})
    return render_template("admin_dashboard_enhanced.html",
                         total_questions=total_questions,
                         total_students=total_students,
                         total_attempts=total_attempts,
                         easy_count=easy_count,
                         medium_count=medium_count,
                         hard_count=hard_count)

@app.route("/admin/ai-generate", methods=["GET", "POST"])
@admin_required
def ai_generate():
    message = ""
    if request.method == "POST":
        if 'file' in request.files and request.files['file'].filename != '':
            file = request.files['file']
            if file.filename.endswith('.pdf'):
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], file.filename)
                file.save(filepath)
                text = extract_text_from_pdf(filepath)
                questions = generate_quiz_from_text(text, 10)
                if questions:
                    for q in questions:
                        q["quiz_id"] = 1
                        db.questions.insert_one(q)
                    message = f"✅ Added {len(questions)} questions from PDF!"
                else:
                    message = "❌ Failed to generate questions from PDF. Please try again."
                os.remove(filepath)
        elif request.form.get('topic'):
            topic = request.form['topic']
            num = int(request.form.get('num_questions', 10))
            model = genai.GenerativeModel('gemini-2.0-flash-exp')
            prompt = f"Create {num} multiple choice questions about {topic}. Return as JSON array with fields: question, options (array of 4), correct (1-4), difficulty (Easy/Medium/Hard). Return ONLY valid JSON array, no other text."
            response = model.generate_content(prompt)
            clean_response = response.text.strip()
            if clean_response.startswith('```json'):
                clean_response = clean_response[7:]
            if clean_response.startswith('```'):
                clean_response = clean_response[3:]
            if clean_response.endswith('```'):
                clean_response = clean_response[:-3]
            questions = json.loads(clean_response)
            for q in questions:
                q["quiz_id"] = 1
                db.questions.insert_one(q)
            message = f"✅ Added {len(questions)} questions about '{topic}'!"
    return render_template("ai_generate.html", message=message)

@app.route("/admin/questions")
@admin_required
def admin_questions():
    questions = list(db.questions.find())
    return render_template("admin_questions.html", questions=questions)

@app.route("/admin/add_question", methods=["GET", "POST"])
@admin_required
def add_question():
    if request.method == "POST":
        new_question = {
            "quiz_id": 1,
            "question": request.form["question"],
            "options": [
                request.form["opt1"],
                request.form["opt2"],
                request.form["opt3"],
                request.form["opt4"]
            ],
            "correct": int(request.form["correct"]),
            "difficulty": request.form.get("difficulty", "Medium")
        }
        db.questions.insert_one(new_question)
        return redirect(url_for("admin_questions"))
    return render_template("add_question_enhanced.html")

@app.route("/admin/delete_question/<question_id>")
@admin_required
def delete_question(question_id):
    from bson.objectid import ObjectId
    db.questions.delete_one({"_id": ObjectId(question_id)})
    return redirect(url_for("admin_questions"))

@app.route("/admin/results")
@admin_required
def admin_results():
    results = list(db.results.find().sort("date", -1))
    return render_template("admin_results.html", results=results)

if __name__ == "__main__":
    app.run(debug=True)