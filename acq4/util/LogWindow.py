import re

from pyqtgraph import FeedbackButton
from pyqtgraph.debug import threadName
from teleprox.log.logviewer import LogViewer

LOG_UI = None


def __reload__(old):
    # preserve old log window
    global LOG_UI
    LOG_UI = old["LOG_UI"]


def get_log_window():
    global LOG_UI
    if LOG_UI is None:
        LOG_UI = LogViewer()
    return LOG_UI


class LogButton(FeedbackButton):
    def __init__(self, *args):
        FeedbackButton.__init__(self, *args)

        self.clicked.connect(get_log_window().show)


def clean_text(text):
    text = re.sub(r"&", "&amp;", text)
    text = re.sub(r">", "&gt;", text)
    text = re.sub(r"<", "&lt;", text)
    text = re.sub(r"\n", "<br/>\n", text)
    # replace indenting spaces with &nbsp
    lines = text.split('\n')
    indents = ['&nbsp;' * (len(line) - len(line.lstrip())) for line in lines]
    lines = [indent + line.lstrip() for indent, line in zip(indents, lines)]
    text = ''.join(lines)
    return text


def format_exception_for_html(entry, exception=None, count=1, entryId=None):
    # Here, exception is a dict that holds the message, reasons, docs, traceback and oldExceptions (which are
    # also dicts, with the same entries). The count and tracebacks keywords are for calling recursively.
    if exception is None:
        exception = entry["exception"]

    text = clean_text(exception["message"])
    text = re.sub(r"^HelpfulException: ", "", text)
    messages = [text]

    if "reasons" in exception:
        reasons = format_reasons_str_for_html(exception["reasons"])
        text += reasons
    if "docs" in exception:
        docs = format_docs_str_for_html(exception["docs"])
        text += docs

    stackText = [format_traceback_for_html(exception["traceback"])]
    text = [text]

    if "oldExc" in exception:
        exc, tb, msgs = format_exception_for_html(entry, exception["oldExc"], count=count + 1)
        text.extend(exc)
        messages.extend(msgs)
        stackText.extend(tb)

    if count != 1:
        return text, stackText, messages
    exc = (
        '<div class="exception"><ol>' + "\n".join([f"<li>{ex}</li>" for ex in text]) + "</ol></div>"
    )
    tbStr = "\n".join(
        [
            f"<li><b>{messages[i]}</b><br/><span class='traceback'>{tb}</span></li>"
            for i, tb in enumerate(stackText)
        ]
    )
    entry["tracebackHtml"] = tbStr

    return f'{exc}<a href="exc:{entryId}">Show traceback {entryId}</a>'


def format_traceback_for_html(tb):
    try:
        tb = [line for line in tb if not line.startswith("Traceback (most recent call last)")]
    except Exception:
        print(f"\n{tb}\n")
        raise

    cleanLines = []
    for i, line in enumerate(tb):
        line = clean_text(line)
        m = re.match(r"(.*)File \"(.*)\", line (\d+)", line)
        if m is not None:
            # insert hyperlink for opening file in editor
            indent, codeFile, lineNum = m.groups()
            extra = line[m.end() :]
            line = f'{indent}File <a href="code:{lineNum}:{codeFile}">{codeFile}</a>, line {lineNum}{extra}'
        cleanLines.append(line)
    return ''.join(cleanLines)


def format_threads_for_html(entry):
    threads = entry["threads"]
    hidden = "\n".join(
        f"<li>Thread <b>{threadName(tid)}</b> ({tid}):<br/>"
        f"<span class='traceback'>{format_traceback_for_html(frames)}</span></li>"
        for tid, frames in threads.items()
    )
    entry["threadsHtml"] = f"<ul>{hidden}</ul>"
    entryId = entry["id"]
    return f'<br/><a href="threads:{entryId}">Show thread states {entryId}</a>'


def format_reasons_str_for_html(reasons):
    # indent = 6
    reasonStr = "<table class='reasons'><tr><td>Possible reasons include:\n<ul>\n"
    for r in reasons:
        r = clean_text(r)
        reasonStr += f"<li>{r}" + "</li>\n"
    reasonStr += "</ul></td></tr></table>\n"
    return reasonStr


def format_docs_str_for_html(docs):
    # indent = 6
    docStr = "<div class='docRefs'>Relevant documentation:\n<ul>\n"
    for _d in docs:
        _d = clean_text(_d)
        docStr += '<li><a href="doc:%s">%s</a></li>\n' % (_d, _d)
    docStr += "</ul></div>\n"
    return docStr
