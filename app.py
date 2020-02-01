from flask import Flask, abort, request
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
        abort(400, error)
        return

    if users_collection.find_one({'email': email}) != None:
        error = 'Email with this account already exists.'
        abort(400, error)
        return

    if users_collection.find_one({'username': username}) != None:
        error = 'Username with this account already exists.'
        abort(400, error)
        return

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

    username = data['username']
    password = data['password']

    error = None

    # make sure parameters are present
    if not username and not email:
        error = 'Username or email is required.'
    elif not password:
        error = 'Password is required.'

    if error != None:
        abort(400, error)
        return

    resp = None
    resp = users_collection.find_one({'email': username})
    if resp == None:
        resp = users_collection.find_one({'username': username})

    if resp == None:
        abort(400, 'No account with that username or email found.')

    if check_password_hash(resp['password'], password):
        return {
            'username': resp['username'],
            'email': resp['email']
        }
    
    abort(400, 'Incorrect password.')
    return

@app.route('/content', methods=['GET'])
def get_user_content():
    email = request.args.get('email')
    resp = entries_collection.find({'email': email})
    resp = list(resp)

    for item in resp:
        item['_id'] = str(item['_id'])

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
        entry_dict['title'] = title_element.string

    metas = soup.find_all('meta')

    for meta in metas:

        if 'name' in meta.attrs and meta.attrs['name'] in important_tags:
            if meta.attrs['name'] == 'keywords':
                entry_dict['keywords'] = meta.attrs['content']
            if meta.attrs['name'] == 'description':
                entry_dict['snippet'] = meta.attrs['content']

    entries_collection.insert_one(entry_dict)

    response = entry_dict
    response['_id'] = str(response['_id'])

    

    return response

@app.route("/entry/edit", methods=['POST'])
def edit_entry():
    data = form_or_json()

    email = data['email']
    entry_id = data['entry_id']
    entry_id = ObjectId(entry_id)

    if email == None:
        abort(400, 'Email not provided')
        return

    if entry_id == None:
        abort(400, 'Entry ID not provided')
        return

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


    entries_collection.update_one(query, {'$set': new_values})
    
    resp_dict = new_values
    resp_dict['_id'] = str(entry_id)
    resp_dict['email'] = email

    return resp_dict

@app.route("/entry/delete", methods=['POST'])
def delete_entry():
    data = form_or_json()

    entry_id = data['entry_id']
    entry_id = ObjectId(entry_id)

    delete_query = {
        '_id': entry_id,
    }

    delete_response = entries_collection.delete_one(delete_query)
    if delete_response.deleted_count == 1:
        return {'status': 'success'}
    else:
        abort(400, 'Error deleting entry - id invalid')
        return


@app.route("/nuke-db", methods=['POST', 'GET'])
def nuke_db():
    entries_collection.remove({})
    users_collection.remove({})
    return {'status': 'Damage is catastrophic. The DB is ravaged. Zero survivors.'}



if __name__ == '__main__':
   app.run(host='0.0.0.0', port=5000)