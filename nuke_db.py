from pymongo import MongoClient

client = MongoClient("mongodb+srv://memex-admin:BLQQqnv29x3SPc8R@cluster0-vnpfv.mongodb.net/test?retryWrites=true&w=majority")
db = client['Memex']

users_collection = db['Users']
entries_collection = db['Entries']

entries_collection.remove({})
users_collection.remove({})
