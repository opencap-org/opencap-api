# OpenCap API
## Workflow for app.opencap.ai
1. User enters the website (app.opencap.ai)
2. The website calls the backend and creates a session
3. The session generates a QR code displayed in the webapp
4. User scans the code with the iOS app. App uses the code to connect directly to the backend
5. User clicks record in the webapp -> this invokes backend to change session state to recording
6. iPhones pull session state every 1sec and see it's in 'recording' state. They start recording
7. User clicks stop recording changing state to 'upload'
8. iPhones upload the videos
9. When all videos are uploaded, backend changes the state to processing and adds videos to the queue for processing
10. Video processing pipeline pools sessions in 'processing' state and processes them
11. After processing, results are sent to the backend and the backend changes its state to 'done'

## Installation

Clone this repo, then:
```
conda create -n opencap python=3.7 
pip install -r requirements.txt
```
Create the `.env` file with all env variables and credentials

## Running the server locally 

```
python manage.py runserver
```

## Adding new fields to the data model

1. Add fields to `mcserver/models.py`
2. Run `python manage.py makemigrations`
3. Run `python manage.py migrate` (be careful, this modifies the database)
4. Add fields we want to expose in the api to the `mcserver/serializers.py` file 

Then for deploying to production we pull all the updated code and run the step 3. (with the production `.env` file)

## Internationalization/Localization

Instructions in this [Link](https://docs.djangoproject.com/en/4.2/topics/i18n/translation/).

**Note:** You must also install [gettext](https://www.gnu.org/software/gettext/). After install, restart your IDE/Terminal).

Inside of mcserver folder:

1. Create files for a language:

   `django-admin makemessages -l <language-code>`

2. Compile messages:

   `django-admin compilemessages`


## Current routes (not up to date, there are more):

/sessions/new/ -> returns session_id and the QR code

/sessions/<session_id>/status/?device_id=<device_id> <- devices use this link to register and get video_id

/sessions/<session_id>/record/ -> server uses this link to start recording

/sessions/<session_id>/stop/ -> server uses this link to stop recording
 
/video/<video_id>/ <- devices use this link to upload the recorded video and parameters  
