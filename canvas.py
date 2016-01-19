from requests.auth import AuthBase
from requests import Session
from pprint import pformat

# From https://stackoverflow.com/a/952952/188792
def flatten(list_of_lists):
    return [item for sublist in list_of_lists for item in sublist]

class PrefixSession(Session):

    def __init__(self, url_prefix):
        self.prefix = url_prefix
        super(PrefixSession, self).__init__()

    @classmethod
    def path_prepend(cls, base, extension):
        "prepend 'base' onto the path 'extension'"
        if base[-1] == "/": base = base[:-1]
        if extension[0] == "/": extension = extension[1:]
        return "/".join((base, extension))

    def request(self, method, url, *args, **kwargs):
        "Prefix the url with the supplied prefix when a request is made"
        if not kwargs.get("skip_prefix", False):
            url = self.path_prepend(self.prefix, url)
        else:
            del kwargs["skip_prefix"]
        return super(PrefixSession, self).request(method, url, *args, **kwargs)

class CanvasError(Exception):

    def __init__(self, response):
        self.response = response

    def __str__(self):
        return repr(self.response)

class CanvasSession(PrefixSession):
    _SPECIAL_ARGS = ["skip_canvas", "include_response"]

    def request(self, method, url, *args, **kwargs):
        fixed_kwargs = kwargs.copy()
        for arg in CanvasSession._SPECIAL_ARGS:
            if arg in fixed_kwargs: del fixed_kwargs[arg]
        response = super(CanvasSession, self).request(method, url, 
                                                      *args, **fixed_kwargs)
        if not kwargs.get("skip_canvas", False):
            if response.status_code != 200:
                raise CanvasError(response)
            json = response.json()
            if kwargs.get("include_response", False):
                return json, response
            else:
                return json
        else:
            return response

class CanvasAuth(AuthBase):

    def __init__(self, access_token):
        self.token = access_token

    def __call__(self, request):
        request.headers["Authorization"] = " ".join(("Bearer", self.token))
        return request

DEBUG = True
if DEBUG:
    from pprint import pprint

class CanvasObject(object):

    def __init__(self, data):
        self._data = data

    def __getitem__(self, key):
        try:
            return self._data[key]
        except KeyError:
            pprint(self._data)
            raise

    def __getattr__(self, key):
        try:
            return self[key]
        except KeyError:
            raise AttributeError(key)

    def __str__(self):
        return "<{0}: {1}>".format(self.__class__.__name__, pformat(self._data))

class CanvasFolder(CanvasObject):

    def is_folder(self): return True
    def is_file(self): return False

class CanvasFile(CanvasObject):

    def is_folder(self): return False
    def is_file(self): return True

class Canvas(object):
    API_PREFIX = "/api/v1/"

    USER_TYPE, COURSE_TYPE, GROUP_TYPE = ("users", "courses", "groups")
    _ROOT_FOLDER_ID = "root"
    OWN_USER_ID = "self"

    def __init__(self, token, domain, scheme="https"):
        full_prefix = "{0}://{1}{2}".format(scheme, domain, Canvas.API_PREFIX)
        self.api = CanvasSession(full_prefix)
        self.api.auth = CanvasAuth(token)

    def _fetch_all(self, url, include_response=False):
        results = []
        while url is not None:
            json, response = self.api.get( url 
                                         , skip_prefix=True
                                         , include_response=True )
            if include_response:
                results.append(json, response)
            else:
                results.append(json)
            url = response.links["next"]["url"] if "next" in response.links else None
        return results

    def _folder_files(self, folder):
        if folder.files_count < 1: return []
        return map(CanvasFile, flatten(self._fetch_all(folder.files_url)))

    def _folder_folders(self, folder):
        if folder.folders_count < 1: return []
        return map(CanvasFolder, flatten(self._fetch_all(folder.folders_url)))

    def folder_list(self, folder):
        return self._folder_folders(folder) + self._folder_files(folder)

    def folder_from_id(self, id):
        return CanvasFolder(self.api.get("/folders/{0}".format(id)))

    def root_folder(self, type, id):
        return CanvasFolder(self.api.get("/{0}/{1}/folders/{2}"\
                                         .format(type, id, Canvas._ROOT_FOLDER_ID)))

    def file_del(self, file):
        self.api.delete("/files/{0}".format(file.id))

    def folder_del(self, folder, recurse=False):
        args = {}
        if recurse:
            args["force"] = 'true'
        self.api.delete("/folders/{0}".format(folder.id), params=args)

    def folder_create(self, parent, name, hidden=False):
        args = {"name": name}
        if hidden: args["hidden"] = 'true'
        return CanvasFolder(self.api.post("/folders/{0}/folders".format(parent.id),
                                          params = args))

