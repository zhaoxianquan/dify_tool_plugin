from enum import Enum

class MimeType(str, Enum):
    CSS = "text/css"
    CSV = "text/csv"
    DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    HTML = "text/html"
    JS = "text/javascript"
    JAVA = "text/x-java-source"
    JSON = "application/json"
    LATEX = "application/x-tex"
    MD = "text/markdown"
    PDF = "application/pdf"
    PHP = "application/x-httpd-php"
    PNG = "image/png"
    PPTX = "application/vnd.openxmlformats-officedocument.presentationml.presentation"
    PY = "text/x-python"
    RST = "text/prs.fallenstein.rst"
    RUBY = "text/x-ruby"
    TXT = "text/plain"
    SH = "application/x-sh"
    SVG = "image/svg+xml"
    XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    XML = "text/xml"
    YAML = "text/yaml"
    ZIP = "application/zip"
