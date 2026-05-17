class ScriptNameMiddleware:

    def __init__(self, app):
        self.app = app

    def __call__(self, environ, start_response):
        script_name = environ.get('HTTP_X_SCRIPT_NAME', '')

        if script_name:
            script_name = script_name.rstrip('/')
            environ['SCRIPT_NAME'] = script_name

            path_info = environ.get('PATH_INFO', '')
            if path_info.startswith(script_name):
                new_path = path_info[len(script_name):]
                environ['PATH_INFO'] = new_path if new_path else '/'

        return self.app(environ, start_response)
