from pymongo import MongoClient

client = MongoClient("mongodb://localhost:27017/")
db = client["quizdb"]

easy = db.questions.count_documents({"difficulty": "Easy"})
medium = db.questions.count_documents({"difficulty": "Medium"})
hard = db.questions.count_documents({"difficulty": "Hard"})
none = db.questions.count_documents({"difficulty": {"$exists": False}})

print(f"Easy: {easy}, Medium: {medium}, Hard: {hard}, No difficulty: {none}")