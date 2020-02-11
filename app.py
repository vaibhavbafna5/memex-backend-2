from flask import Flask, abort, request, jsonify
from pymongo import MongoClient
from bs4 import BeautifulSoup
from flask_cors import CORS
from datetime import date
from bson import ObjectId
from werkzeug.security import check_password_hash, generate_password_hash

import requests
import gunicorn
import json

class JSONEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, ObjectId):
            return str(o)
        return json.JSONEncoder.default(self, o)

app = Flask(__name__)
CORS(app)

client = MongoClient("mongodb+srv://memex-admin:BLQQqnv29x3SPc8R@cluster0-vnpfv.mongodb.net/test?retryWrites=true&w=majority")
db = client['Memex']

users_collection = db['Users']
entries_collection = db['Entries']
tags_collection = db['Tags']

important_tags = {'title', 'keywords', 'description', }

def form_or_json():
    data = request.get_json(silent=True)
    return data if data is not None else request.form

def flatten_data(entry):
    data = ''
    if entry['tags'] != None:
        for tag in entry['tags']:
            data += tag.lower()
            data += " "
            
    if entry['notes'] != None:
        data += entry['notes'].lower()
        data += " "
    
    if entry['title'] != None:
        data += entry['title'].lower()
        data += " "
        
    if entry['keywords'] != None:
        data += entry['keywords'].lower()
        data += " "
        
    if entry['snippet'] != None:
        data += entry['snippet'].lower()
        data += " "
    
    return data

@app.route("/")
def index():
    return "merp merp 2020"

@app.route('/register', methods=['POST'])
def register_user():
    data = form_or_json()

    username = data['username']
    password = data['password']
    email = data['email']

    error = None

    # make sure parameters are present
    if not username:
        error = 'Username is required.'
    elif not password:
        error = 'Password is required.'
    elif not email:
        error = 'Email is required.'

    if error != None:
        return {'error': error}, 400

    if users_collection.find_one({'email': email}) != None:
        error = 'Email with this account already exists.'
        return {'error': error}, 400

    if users_collection.find_one({'username': username}) != None:
        error = 'Username with this account already exists.'
        return {'error': error}, 400

    user_dict = {
        'username': username,
        'email': email,
        'password': generate_password_hash(password),
    }

    resp = users_collection.insert_one(user_dict)

    response = {
        'status': 'success',
        'username': username,
        'email': email,
    }

    return response


@app.route('/login', methods=['POST'])
def login_user():
    data = form_or_json()

    username = data['username'] or data['email']
    password = data['password']

    error = None

    # make sure parameters are present
    if not username:
        error = 'Username or email is required.'
    elif not password:
        error = 'Password is required.'

    if error != None:
        return {"error": error}, 400

    resp = None
    
    resp = users_collection.find_one({'email': username})
    if resp == None:
        resp = users_collection.find_one({'username': username})

    if resp == None:
        return {"error": "No account with that username or email found."}, 400

    if check_password_hash(resp['password'], password):
        return {
            'username': resp['username'],
            'email': resp['email']
        }

    return {"error": "Invalid password"}, 400

@app.route('/content', methods=['GET'])
def get_user_content():
    email = request.args.get('email')
    resp = entries_collection.find({'email': email})
    resp = list(resp)

    for item in resp:
        item['_id'] = str(item['_id'])

    resp.reverse()

    return {'entries': resp}

@app.route('/entry/create', methods=['POST'])
def create_user_entry():
    data = form_or_json()

    email = data['email']
    url = data['url']
    tags = data['tags']
    notes = data['notes']

    error = None

    if email == None:
        error = 'Email is not present.'
        abort(400, error)
        return

    if url == None:
        error = 'Url is not present.'
        abort(400, error)
        return

    entry_dict = {
        'email': email,
        'url': url,
        'tags': tags,
        'notes': notes,
        'title': '',
        'keywords': '',
        'snippet': '',
        'add-date': date.today().strftime("%B %d, %Y"),
    }

    html_response = requests.get(url)
    soup = BeautifulSoup(html_response.text)

    # parse relevant fields
    title_element = soup.find('title')
    if title_element != None:
        entry_dict['title'] = title_element.string.strip(" ")

    metas = soup.find_all('meta')

    for meta in metas:

        if 'name' in meta.attrs and meta.attrs['name'] in important_tags:
            if meta.attrs['name'] == 'keywords': 
                entry_dict['keywords'] = meta.attrs['content']
            if meta.attrs['name'] == 'description':
                entry_dict['snippet'] = meta.attrs['content']

    # add to entries collection
    entries_collection.insert_one(entry_dict)

    response = entry_dict
    response['_id'] = str(response['_id'])

    # add to tags collection
    if tags:
        entry_id = ObjectId(response['_id'])
        for tag in tags:
            res = tags_collection.find_one({'tag': tag, 'email': email})
            if res:
                tags_query = {'tag': tag, 'email': email}
                entries = res['entries']
                entries.append(entry_id)
                tags_collection.update_one(tags_query, {'$set': {'entries': entries}})
            else:
                tags_dict = {
                    'tag': tag,
                    'email': email,
                    'entries': [entry_id]
                }
                tags_collection.insert_one(tags_dict)

    return response

@app.route("/entry/edit", methods=['POST'])
def edit_entry():
    data = form_or_json()

    email = data['email']
    entry_id = data['entry_id']
    entry_id = ObjectId(entry_id)

    if email == None:
        return {'error': 'Email not provided'}, 400

    if entry_id == None:
        return {'error': 'Entry ID not provided'}, 400

    notes = data['notes']
    snippet = data['snippet']
    url = data['url']
    tags = data['tags']
    title = data['title']

    query = {
        '_id': entry_id,
        'email': email,
    }

    new_values = {
        'notes': notes,
        'snippet': snippet,
        'url': url,
        'tags': tags,
        'title': title,
    }

    # get old entry & list of tags to be removed
    old_entry = entries_collection.find_one({'_id': entry_id})
    old_tags = old_entry['tags']

    # update entries collection
    entries_collection.update_one(query, {'$set': new_values})

    # remove tags that are no longer present
    if tags:
        new_tags = tags
    else:
        new_tags = []
    tags_to_remove = []
    
    if old_tags:
        for old_tag in old_tags:
                if old_tag not in new_tags:
                    tags_to_remove.append(old_tag)
                    old_tag_res = tags_collection.find_one({'tag': old_tag, 'email': email})
                    
                    if len(old_tag_res['entries']) == 1:
                        tags_collection.delete_one({'tag': old_tag, 'email': email})
                    else:
                        new_entries = old_tag_res['entries']
                        new_entries.remove(entry_id)
                        tags_query = {'tag': old_tag, 'email': email}
                        tags_collection.update_one(tags_query, {'$set': {'entries': new_entries}})


    # create new tags in tags collection
    if tags:
        for tag in tags:
            res = tags_collection.find_one({'tag': tag, 'email': email})
        
            if res:
                tags_query = {'tag': tag, 'email': email}
                entries = res['entries']
                
                if entry_id not in entries:
                    entries.append(entry_id)
                    tags_collection.update_one(tags_query, {'$set': {'entries': entries}})
            else:
                tags_dict = {
                    'tag': tag,
                    'email': email,
                    'entries': [entry_id]
                }
                tags_collection.insert_one(tags_dict)
    
    # response dictionary
    resp_dict = new_values
    resp_dict['_id'] = str(entry_id)
    resp_dict['email'] = email

    return resp_dict

@app.route("/entry/delete", methods=['POST'])
def delete_entry():
    data = form_or_json()

    entry_id = data['entry_id']
    email = data['email']

    entry_id = ObjectId(entry_id)

    # delete entries in tag
    entry_to_delete = entries_collection.find_one({'_id': entry_id})
    tags_to_delete = entry_to_delete['tags']

    if tags_to_delete:
        for tag_to_delete in tags_to_delete:
            resp = tags_collection.find_one({'tag': tag_to_delete, 'email': email})

            if len(resp['entries']) == 1:
                tags_collection.delete_one({'tag': tag_to_delete, 'email': email})
            else:
                new_entries = resp['entries']
                new_entries.remove(entry_id)
                tags_query = {'tag': tag_to_delete, 'email': email}
                tags_collection.update_one(tags_query, {'$set': {'entries': new_entries}})

    # delete actual entry from entries collection
    delete_query = {
        '_id': entry_id,
    }

    delete_response = entries_collection.delete_one(delete_query)
    if delete_response.deleted_count == 1:
        return {'status': 'success'}
    else:
        abort(400, 'Error deleting entry - id invalid')
        return

@app.route("/search", methods=['GET'])
def search_entries():
    email = request.args.get('email')
    query = request.args.get('query')

    query = query.rstrip(" ")

    queries = query.split(" ")
    user_entries = entries_collection.find({'email': email})
    user_entries = list(user_entries)
    
    results = {}
    
    for term in queries:
        
        term = term.lower()
        hits = 0

        for user_entry in user_entries:
            data = flatten_data(user_entry)
            entry = user_entry
            entry['_id'] = str(entry['_id'])
            
            if term in data:
                results[entry['_id']] = entry
                hits += 1
                
        if hits == 0:
            return {}

    return results


@app.route("/filter", methods=['GET'])
def get_entries_by_tag():
    email = request.args.get('email')
    tag = request.args.get('tag')

    resp = tags_collection.find_one({'tag': tag, 'email': email})
    entries = resp['entries']

    response_entries = []
    for entry in entries:
        entry_resp = entries_collection.find_one({'_id': entry})
        entry_resp['_id'] = str(entry_resp['_id'])
        response_entries.append(entry_resp)

    return {'entries': response_entries} 

@app.route("/user-tags", methods=['GET'])
def get_all_user_tags():
    email = request.args.get('email')
    tags = tags_collection.find({'email': email})
    tags = list(tags)
    tag_names = set()
    
    for tag in tags:
        tag_names.add(tag['tag'])

    return {'tags': list(tag_names)}



@app.route("/nuke-db", methods=['POST', 'GET'])
def nuke_db():
    entries_collection.remove({})
    users_collection.remove({})
    tags_collection.remove({})
    return {'status': 'Damage is catastrophic. The DB is ravaged. Zero survivors.'}



if __name__ == '__main__':
   app.run(host='0.0.0.0', port=5000)