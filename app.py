import streamlit as st
from pytube import YouTube
import os
import pandas as pd
from st_clickable_images import clickable_images
import requests
from time import sleep
from dotenv import load_dotenv

import os
from dotenv import load_dotenv

# Load environment variables from the .env file
load_dotenv()

# Access the API key
assemblyai_api_key = os.getenv("ASSEMBLYAI_API_KEY")

# Check if the API key is loaded successfully
if assemblyai_api_key is None:
    raise ValueError("ASSEMBLYAI_API_KEY is not set in the .env file.")


upload_endpoint = "https://api.assemblyai.com/v2/upload"
transcript_endpoint = "https://api.assemblyai.com/v2/transcript"
headers = {
    "authorization": assemblyai_api_key,
    "content-type": "application/json"
}


@st.experimental_memo
def save_audio(url):
    yt = YouTube(url)
    video = yt.streams.filter(only_audio=True).first()
    out_file = video.download()
    base, ext = os.path.splitext(out_file)
    file_name = base + '.mp3'

    # Check if the file already exists, and if so, append a unique identifier
    counter = 1
    while os.path.exists(file_name):
        file_name = f"{base}_{counter}.mp3"
        counter += 1

    os.rename(out_file, file_name)
    print(yt.title + " has been successfully downloaded.")
    print(file_name)
    return yt.title, file_name, yt.thumbnail_url

@st.experimental_memo
def upload_to_AssemblyAI(save_location):
    CHUNK_SIZE = 5242880

    def read_file(filename):
        with open(filename, 'rb') as _file:
            while True:
                print("chunk uploaded")
                data = _file.read(CHUNK_SIZE)
                if not data:
                    break
                yield data

    upload_response = requests.post(
        upload_endpoint,
        headers=headers,
        data=read_file(save_location)
    )
    print(upload_response.json())
    

    audio_url = upload_response.json()['upload_url']
    print('Uploaded to', audio_url)

    return audio_url

@st.cache_data
def start_analysis(audio_url):
	
	## Start transcription job of audio file
	data = {
	    'audio_url': audio_url,
	    'iab_categories': True,
	    'content_safety': True,
	    "summarization": True,
	}
	
	transcript_response = requests.post(transcript_endpoint, json=data, headers=headers)
	print(transcript_response)
	st.write(transcript_response.json())

	transcript_id = transcript_response.json()['id']
	polling_endpoint = transcript_endpoint + "/" + transcript_id
	
	print("Transcribing at", polling_endpoint)
	return polling_endpoint

@st.experimental_memo
def get_analysis_results(polling_endpoint):

    status = 'submitted'

    while True:
        print(status)
        polling_response = requests.get(polling_endpoint, headers=headers)
        status = polling_response.json()['status']
        st.write(polling_response.json())

        if status == 'submitted' or status == 'processing' or status == 'queued':
            print('not ready yet')
            sleep(10)
        
        elif status == 'completed':
            print('creating transcript')
            return polling_response  # Correct indentation
            break  # Correct indentation
        
        else:
            print('error')
            return False  # Correct indentation
            break  # Correct indentation


st.title(" youtube channel analyzer")
st.markdown("With this app you can audit a Youtube channel to see if you'd like to sponsor them. All you have to do is to pass a list of links to the videos of this channel and you will get a list of thumbnails. Once you select a video by clicking its thumbnail, you can view:")
st.markdown("1. a summary of the video,")
st.markdown("2. the topics that are discussed in the video,")
st.markdown("3. whether there are any sensitive topics discussed in the video.")
st.markdown("Make sure your links are in the format: <https://www.youtube.com/watch?v=HfNnuQOHAaw> and not <https://youtu.be/HfNnuQOHAaw>")

default_bool = st.checkbox('Use default example file', )

titles = []  # Initialize the titles list outside of the conditional block
locations = []
thumbnails = []

if default_bool:
    file = open('./links.txt')
else:
    file = st.file_uploader('Upload a file that includes the video links (.txt)')

if file is not None:
    print(file)
    dataframe = pd.read_csv(file, header=None)
    dataframe.columns = ['video_url']
    urls_list = dataframe["video_url"].tolist()
    
    for video_url in urls_list:
        video_title, save_location, thumbnail_url = save_audio(video_url)
        titles.append(video_title)
        locations.append(save_location)
        thumbnails.append(thumbnail_url)


    selected_video = clickable_images(thumbnails,
    titles = titles,
    div_style={"height": "400px", "display": "flex", "justify-content": "center", "flex-wrap": "wrap", "overflow-y":"auto"},
    img_style={"margin": "5px", "height": "150px"}
    )

    st.markdown(f"Thumbnail #{selected_video} clicked" if selected_video > -1 else "No image clicked")
    
    if selected_video > -1:
        video_url = urls_list[selected_video]
        video_title = titles[selected_video]
        save_location = locations[selected_video]
      
        st.header(video_title)
        st.audio(save_location)

        audio_url = upload_to_AssemblyAI(save_location)
        
        polling_endpoint = start_analysis(audio_url)

        results = get_analysis_results(polling_endpoint)

        summary = results.json()['summary']
        topics = results.json()['iab_categories_result']['summary']
        sensitive_topics = results.json()['content_safety_labels']['summary']

        st.header("Summary of this video")
        st.write(summary)

        st.header("Sensitive content")
        if sensitive_topics != {}:
           st.subheader('🚨 Mention of the following sensitive topics detected.')
           moderation_df = pd.DataFrame(sensitive_topics.items())
           moderation_df.columns = ['topic','confidence']
           st.dataframe(moderation_df, use_container_width=True)
        else:
                    st.subheader('✅ All clear! No sensitive content detected.')

        st.header("Topics discussed")
        topics_df = pd.DataFrame(topics.items())
        topics_df.columns = ['topic','confidence']
        topics_df["topic"] = topics_df["topic"].str.split(">")
        expanded_topics = topics_df.topic.apply(pd.Series).add_prefix('topic_level_')
        topics_df = topics_df.join(expanded_topics).drop('topic', axis=1).sort_values(['confidence'], ascending=False).fillna('')

        st.dataframe(topics_df)