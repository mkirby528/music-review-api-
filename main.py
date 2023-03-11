import simplejson as json
import boto3
import os
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
from dotenv import load_dotenv
from datetime import date
from datetime import datetime
from boto3.dynamodb.conditions import Key

if os.getenv("TABLE_NAME") is None:
    load_dotenv("./.env")


auth_manager = SpotifyClientCredentials()
spotify = spotipy.Spotify(auth_manager=SpotifyClientCredentials())


def lambda_handler(event, context):
    dynamodb_resource = boto3.resource("dynamodb")
    TABLE_NAME = os.environ["TABLE_NAME"]
    table = dynamodb_resource.Table(TABLE_NAME)

    method = event.get('httpMethod', '').upper()
    headers = event.get('headers', {})
    query_params = event.get('queryStringParameters', {})
    print(f"Headers: {headers}")
    print(f"Query Paramaters: {query_params}")
    if method == "GET":
        response = None
        if not "Title" in query_params:
            response = get_all_albums(table, query_params)
        else:
            response = get_album(table, query_params)
        if not response:
            return format_response(404)
        return format_response(200, response)

    if method == "POST":
        body = event.get('body', {})
        album_item = json.loads(body)
        dynamo_response = create_album_record(table, album_item)
        return format_response(201, dynamo_response)

    if method == "DELETE":
        print("DELETE request")

    if method == "PATCH":
        print("PATCH request")


def format_response(status_code, response_body={}):
    return {
        'statusCode': status_code,
        'body': json.dumps(response_body)
    }


def create_album_record(table, album):
    title = album["Title"]
    artist = album["Artist"]
    album["Type"] = "ALBUM"
    album = add_album_metadata(album, title, artist)
    print(album)
    response = table.put_item(Item=album)
    return (response)


def get_all_albums(table, query_params):
    albums = table.scan()["Items"]
    sort_key = query_params.get("sort_key", "Title")
    sort_order = query_params.get("sort_order", "")
    is_descending = False
    if sort_key not in ("Title", "Rating", "Artist", "DateListened", "ReleaseDate"):
        return False
    if sort_order.lower() in ("desc", "descending"):
        is_descending = True
    return sorted(albums, key=lambda d: d[sort_key], reverse=is_descending)


def get_album(table, query_params):
    if query_params and "Title" in query_params:
        title = query_params["Title"]
        response = table.query(KeyConditionExpression=Key('Title').eq(title))
        items = response["Items"]
        if not items:
            return None
        return items[0]


def add_album_metadata(album, title, artist):
    query_string = f"{title} artist:{artist}"
    print(query_string)
    results = spotify.search(
        q=query_string, type='album')
    print(results)
    if len(results['albums']['items']) == 0:
        query_string = f"{title}"
        results = spotify.search(
            q=query_string, type='album')
    seach_result = results['albums']['items'][0]
    spotify_album = spotify.album(seach_result["id"])
    album["id"] = spotify_album["id"]
    if spotify_album["release_date_precision"] == "day":
        album["ReleaseDate"] = datetime.strptime(
            spotify_album["release_date"], '%Y-%m-%d').strftime('%m/%d/%Y')
    else:
        album["ReleaseDate"] = spotify_album["release_date"]
    album["SpotifyURI"] = spotify_album["external_urls"]["spotify"]
    album["ImageLarge"] = spotify_album["images"][0]["url"]
    album["ImageMedium"] = spotify_album["images"][1]["url"]
    album["ImageSmall"] = spotify_album["images"][2]["url"]
    album["NumberOfTracks"] = spotify_album["total_tracks"]
    if not "DateListened" in album:
        album["DateListened"] = date.today().strftime("%m/%d/%Y")
    if not "HaveVinyl" in album:
        album["HaveVinyl"] = False
    return album
