from pymongo import MongoClient

# Connect to MongoDB
client = MongoClient("mongodb://localhost:27017/")
db = client["quizdb"]

# Count total questions
total_questions = db.questions.count_documents({})
print(f"📊 Found {total_questions} questions in database")

# Add difficulty to all existing questions
count = 0
for q in db.questions.find():
    db.questions.update_one(
        {"_id": q["_id"]},
        {"$set": {"difficulty": "Medium"}}
    )
    count += 1
    print(f"✅ Updated question {count}: {q['question'][:30]}...")

print(f"\n🎉 COMPLETE! Added 'difficulty: Medium' to all {count} questions!")

# Verify
sample = db.questions.find_one()
print(f"\n📝 Sample question now has: {sample.get('difficulty', 'NOT FOUND')}")