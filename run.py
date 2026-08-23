from app import create_app, socketio

app = create_app()

if __name__ == '__main__':
    # For local development allow the Werkzeug server even when Flask-SocketIO
    # warns against using it in production. This makes it easier to run
    # the app directly with `python run.py` in dev environments.
    socketio.run(app, debug=True, host='0.0.0.0', port=5000, allow_unsafe_werkzeug=True)
