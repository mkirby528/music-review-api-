import simplejson as json
import re
import boto3
import os
import spotipy
import src.constants as constants
from spotipy.oauth2 import SpotifyClientCredentials
from dotenv import load_dotenv
from datetime import date
from datetime import datetime
from boto3.dynamodb.conditions import Key
from src.utils.response_utils import format_response
from src.utils.spotify import build_album_object
if os.getenv("TABLE_NAME") is None:
    load_dotenv("./.env")


auth_manager = SpotifyClientCredentials(cache_path="/tmp/.cache")
spotify = spotipy.Spotify(auth_manager=SpotifyClientCredentials())
dynamodb_resource = boto3.resource("dynamodb")
TABLE_NAME = os.environ["TABLE_NAME"]
table = dynamodb_resource.Table(TABLE_NAME)


def lambda_handler(event, context):
    # Read and process request elements
    path = event.get('path', '')
    path_paramaters = event.get("pathParameters", {})
    method = event.get('httpMethod', '').upper()
    headers = event.get('headers', {})
    query_params = event.get('queryStringParameters')
    body = event.get('body', {})

    if not query_params:
        query_params = {}
    print(f'Method: {method}')
    print(f"Path: {path}")
    print(f"Path Parameters: {path_paramaters}")
    print(f"Headers: {headers}")
    print(f"Query Paramaters: {query_params}")
    print(f"Body: {body}")

    if method == "GET":
        response = None
        if path_paramaters and path_paramaters["albumID"]:
            album_id = path_paramaters.get("albumID", "")
            response = get_album(album_id)
        else:
            response = get_all_albums(query_params)
        if not response:
            return format_response(404)
        return format_response(200, response)

    if method == "POST":
        album_item = json.loads(body)
        album_object = build_album_object(spotify, album_item)
        print("================")
        print(album_object)
        print("================")
        response = table.put_item(Item=album_object)
        return format_response(201, response)

    if method == "PATCH":
        album_id = path_paramaters.get("albumID", "")
        if not album_id:
            return (400, "No albumID provided.")
        if bool(re.search(constants.ADD_VINYL_PATH_REGEX, path)):
            return format_response(200, addVinylRecord(album_id))
        else:
            update_fields = json.loads(body)
            album = update_album(album_id, update_fields)

            return format_response(200, album)
    if method == "DELETE":
        album_id = path_paramaters.get("albumID", "")
        if not album_id:
            return (400, "No albumID provided.")
        response = table.delete_item(
            Key={
                'id': album_id
            }
        )
        return format_response(200, response)


def addVinylRecord(album_id):
    album = update_album(album_id, {"HaveVinyl": True})
    if album:
        return True


def create_album_record(album):
    title = album["Title"]
    artist = album["Artist"]
    album["Type"] = "ALBUM"
    album = add_album_metadata(album, title, artist)
    #
    return album


def update_album(album_id, fields_to_update):
    album = table.query(KeyConditionExpression=Key(
        'id').eq(album_id))["Items"][0]
    print(f"Updating album `{album['Title']}`... ")
    print(f"Fields to update: {fields_to_update}")
    update_expressions = []
    expression_attribute_values = {}
    count = 0
    for field, value in fields_to_update.items():
        if field not in album:
            print(f"Field `{field}` not present on original object")
            return False
        update_expressions.append(f'{field}= :var{count}')
        expression_attribute_values[f":var{count}"] = value
        count += 1
    return table.update_item(
        Key={
            'id': album_id
        },
        UpdateExpression="SET " + ",".join(update_expressions),
        ExpressionAttributeValues=expression_attribute_values,
        ReturnValues="ALL_NEW"
    )


def get_all_albums(query_params):
    albums = table.scan()["Items"]
    sort_key = query_params.get("sort_key", "Title")
    sort_order = query_params.get("sort_order", "asc")
    is_descending = False
    if sort_key not in ("Title", "Rating", "Artist", "DateListened", "ReleaseDate"):
        return False
    if sort_order.lower() in ("desc", "descending"):
        is_descending = True
    if sort_key == "Rating":
        return sorted(albums, key=lambda d: int(d[sort_key]), reverse=is_descending)
    return sorted(albums, key=lambda d: d[sort_key], reverse=is_descending)


def get_album(album_id):
    print(f"Getting album...  id: {album_id}")
    response = table.query(KeyConditionExpression=Key('id').eq(album_id))
    items = response["Items"]
    if not items:
        return None
    return items[0]
