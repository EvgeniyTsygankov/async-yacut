import re


ALLOWED_EXTS = ['jpg', 'jpeg', 'png', 'gif', 'bmp', 'py', 'txt', 'md']
SHORT_AUTO_GENERATE_LENGTH = 6
MAX_LENGHT_SHORT_LINK = 16
MAX_TRIES = 100
RESERVED_SHORTS = {'files'}
SHORT_PATTERN = r'^[A-Za-z0-9]{1,6}$'
SHORT_RE = re.compile(SHORT_PATTERN)