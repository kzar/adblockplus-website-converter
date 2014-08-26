#!/usr/bin/env python
# coding: utf-8

import sys, os, re, json, errno, codecs, itertools
from collections import OrderedDict
from xml.dom import minidom, Node
import HTMLParser
h = HTMLParser.HTMLParser()

output_dir = "../wwwnew"
input_dir = "../www"
locales = ("ar", "bg", "de", "en", "es", "fr", "he", "hu", "ko", "lt", "nl", "pt_BR", "ru", "sk", "zh_CN", "zh_TW")

def ensure_dir(path):
  try:
    os.makedirs(os.path.dirname(path))
  except OSError, e:
    if e.errno != errno.EEXIST:
      raise

def read_xml(path):
  with open(path, "rb") as handle:
    xml = handle.read()
    xml = re.sub(r"(?<!&)&(?!#?\w+;|&)", "&amp;", xml)
    xml = xml.replace(' href="en/', ' href="')
    xml = xml.replace(' href="en"', ' href="index"')
    xml = xml.replace(' src="en/', ' src="')
    xml = re.sub(r"</?fix/?>", "", xml, flags=re.S)
    return minidom.parseString("<!DOCTYPE root [<!ENTITY mdash \"&#8212;\"><!ENTITY nbsp \"&#xA0;\"><!ENTITY copy \"&#169;\">]><root>%s</root>" % xml)

def save_locale(path, data):
  ensure_dir(path)
  with codecs.open(path, "wb", encoding="utf-8") as handle:
    json.dump(data, handle, ensure_ascii=False, indent=2, separators=(',', ': '))

def get_text(node):
  result = []
  for child in node.childNodes:
    if child.nodeType != Node.TEXT_NODE:
      print child.tagName
      raise Exception("Unexpected node type %i" % child.nodeType)
    result.append(child.nodeValue)
  return "".join(result)

def get_element(node, tagName, *args):
  for child in node.childNodes:
    if child.nodeType == Node.ELEMENT_NODE and child.tagName == tagName:
      if args:
        return get_element(child, *args)
      else:
        return child
  return None

def merge_children(nodes):
  def is_text(node):
    if node.nodeType == Node.TEXT_NODE:
      return True
    if (node.nodeType == Node.ELEMENT_NODE and
        node.tagName in ("em", "strong") and
        len(node.attributes) == 0 and
        len(node.childNodes) == 1 and
        node.firstChild.nodeType == Node.TEXT_NODE):
      return True
    if (node.nodeType == Node.ELEMENT_NODE and
        node.tagName == "a" and
        len(node.attributes) == 1 and
        node.hasAttribute("href") and
        len(node.childNodes) == 1 and
        node.firstChild.nodeType == Node.TEXT_NODE):
      return True
    if (node.nodeType == Node.ELEMENT_NODE and
        node.tagName == "a" and
        not node.hasAttribute("href") and
        len(node.childNodes) == 2 and
        node.firstChild.nodeType == Node.ELEMENT_NODE and
        node.firstChild.tagName == "attr" and
        node.lastChild.nodeType == Node.TEXT_NODE):
      return True
    return False

  def is_empty(node):
    return node.nodeType == Node.TEXT_NODE and not node.nodeValue.strip()

  i = 0
  en = nodes["en"]
  start = None
  for i in range(len(en.childNodes) + 1):
    if start == None:
      if i < len(en.childNodes) and is_text(en.childNodes[i]):
        start = i
    elif i >= len(en.childNodes) or not is_text(en.childNodes[i]):
      end = i - 1
      while start < end and is_empty(en.childNodes[start]):
        start += 1
      while start < end and is_empty(en.childNodes[end]):
        end -= 1
      if start < end:
        for locale, parent in nodes.iteritems():
          if end < len(parent.childNodes):
            text = []
            links = []
            for child in parent.childNodes[start:end+1]:
              if child.nodeType == Node.ELEMENT_NODE and child.tagName == "a":
                # Squash attr tags into a tags now so link strings are generated properly
                for grandchild in child.childNodes:
                  if grandchild.nodeType == Node.ELEMENT_NODE and grandchild.tagName == "attr":
                    child.setAttribute(grandchild.getAttribute("name"), get_text(grandchild))
                    child.removeChild(grandchild)
                links.append(child.getAttribute("href"))
                child.removeAttribute("href")
              text.append(child.toxml())
            node = parent.ownerDocument.createTextNode("".join(text))
            node.links = links
            parent.replaceChild(node, parent.childNodes[start])
            for child in parent.childNodes[start+1:end+1]:
              parent.removeChild(child)
          else:
            while start < len(parent.childNodes):
              parent.removeChild(parent.childNodes[start])
        i -= end - start
      start = None

def process_body(nodes, strings, counter=1):
  if nodes["en"].nodeType == Node.ELEMENT_NODE:
    if nodes["en"].tagName not in ("style", "script", "fix"):
      merge_children(nodes)
      for i in range(len(nodes["en"].childNodes)):
        new_nodes = {}
        for locale, value in nodes.iteritems():
          if len(value.childNodes) > i:
            new_nodes[locale] = value.childNodes[i]
        counter = process_body(new_nodes, strings, counter)
  elif nodes["en"].nodeType == Node.TEXT_NODE:
    if nodes["en"].nodeValue.strip():
      if hasattr(nodes["en"], "links") and len(nodes["en"].links):
        links = "(%s)" % ", ".join(nodes["en"].links)
      else:
        links = ""
      # If an identical string has been stored on this page reuse it
      try:
        string_key = strings["en"].keys()[strings["en"].values().index({"message": nodes["en"].nodeValue.strip()})]
      except ValueError:
        string_key = "s%i" % counter
      for locale, value in nodes.iteritems():
        text = value.nodeValue or ""
        pre, text, post = re.search(r"^(\s*)(.*?)(\s*)$", text, re.S).groups()
        if string_key == "s%i" % counter and text and text.find("[untr]") < 0:
          text = re.sub("\n\s+", " ", text, flags=re.S)
          strings[locale][string_key] = {"message": h.unescape(text)}
        value.nodeValue = "%s$%s%s$%s" % (pre, string_key, links, post)
      counter += 1
  elif nodes["en"].nodeType == Node.COMMENT_NODE:
    pass
  else:
    print >>sys.stderr, "Unexpected node type %i" % nodes["en"].nodeType

  return counter

def process_page(path, menu):
  pagename = os.path.join(os.path.dirname(path), os.path.basename(path).replace("page!", ""))
  if "/" not in pagename:
    pagename = os.path.join(pagename, "index")
    format = "page!%s"
  else:
    format = "%s/" + path.split("/", 1)[1]
  pagename = pagename.split("/", 1)[1]

  data = {}
  strings = {}
  for locale in locales:
    if not os.path.exists(format % locale):
      continue
    data[locale] = read_xml(format % locale)
    strings[locale] = OrderedDict()

  for locale in data.iterkeys():
    title = get_text(get_element(data[locale].documentElement, "title", "anwv")).strip()
    if title and title.find("[untr]") < 0:
      strings[locale]["title"] = {"message": title}

  titlestring = "title"
  if pagename in menu["en"]:
    if menu["en"][pagename]["message"] != strings["en"]["title"]["message"]:
      titlestring = "title-full"
      for locale in locales:
        if locale in strings and "title" in strings[locale]:
          title = strings[locale]["title"]
          if locale in menu and pagename in menu[locale]:
            strings[locale]["title"] = menu[locale][pagename]
          else:
            del strings[locale]["title"]
          strings[locale]["title-full"] = title
    for locale in locales:
      if locale in menu and pagename in locale:
        del menu[locale][pagename]

  bodies = {}
  for locale, value in data.iteritems():
    bodies[locale] = get_element(value.documentElement, "body", "anwv")
    if pagename == "index":
      container = get_element(bodies[locale], "div")
      container.setAttribute("id", "install-container")
      container.setAttribute("class", "{{page}}")
  process_body(bodies, strings)

  body = re.sub(r"</?anwv/?>", "", bodies["en"].toxml())
  head = re.sub(r"</?anwv/?>", "", get_element(data["en"].documentElement, "head", "anwv").toxml())
  if head:
    pagedata = "<head>%s</head>%s" % (head, body)
  else:
    pagedata = body

  pagedata = pagedata.replace("/_override-static/global/global", "")

  # <foo><attr name="bar">test</attr> => <foo bar="test">
  pagedata = re.sub(r'>\s*<attr\s+name="(\w+)">([^"<>]*)</attr\b', r' \1="\2"', pagedata, flags=re.S)

  # <script src=""/> => <script src=""></script>
  pagedata = re.sub(r'<((?!link\b|meta\b|br\b|col\b|base\b|img\b|param\b|area\b|hr\b|input\b)([\w:]+)\b[^<>]*)/>', r'<\1></\2>', pagedata, flags=re.S)

  # <img src="foo"/> => <img src="foo">
  pagedata = re.sub(r'\/>', r'>', pagedata)

  # <img src="foo">dummy</img> => <img src="foo">
  pagedata = re.sub(r'<((link|meta|br|col|base|img|param|area|hr|input)\b[^<>]*)>([^<>]*)</\2>', r'<\1>', pagedata, flags=re.S)

  def translate_tabs(tabstop = 8):
    offset = 0
    def replace(match, offset=offset):
      offset += match.start(0)
      return " " * (tabstop - offset % tabstop)
    return replace

  # Remove some trailing whitespace and replace tabs with spaces
  pagedata = "\n".join([re.sub(r'\t', translate_tabs(8), s) for s in pagedata.split("\n")])
  pagedata = re.sub(r'\ +\n', '\n', pagedata, flags=re.S)

  if pagename == "index":
    def translate_tag(match):
      return r'{{"%s"|translate(links=[%s])}}' % (match.group(1), '"%s"' % '", "'.join(match.group(2).split(", ")))

    pagedata = re.sub(r"\$([\w\-]+)\$", r'{{"\1"|translate}}', pagedata)
    pagedata = re.sub(r"\$([\w\-]+)\((.*?)\)\$", lambda match: translate_tag(match), pagedata)
    pagedata = "noheading=True\nlocalefile=index\n\n%s" % pagedata
  elif titlestring != "title":
    pagedata = "title=%s\n\n%s" % (titlestring, pagedata)

  if pagename == "index":
    target = os.path.join(output_dir, "includes", pagename + ".tmpl")
  else:
    target = os.path.join(output_dir, "pages", pagename + ".raw")
  ensure_dir(target)
  with codecs.open(target, "wb", encoding="utf-8") as handle:
    handle.write(pagedata)

  for locale, value in strings.iteritems():
    if value:
      localefile = os.path.join(output_dir, "locales", locale, pagename + ".json")
      save_locale(localefile, value)

def process_image(path):
  if path.startswith("en/"):
    target = os.path.join(output_dir, "locales", os.path.dirname(path), os.path.basename(path).replace("image!", ""))
  else:
    target = os.path.join(output_dir, "static", os.path.dirname(path), os.path.basename(path).replace("image!", ""))
  with open(path, "rb") as handle:
    data = handle.read()

  ensure_dir(target)
  with open(target, "wb") as handle:
    handle.write(data)

def process_file(path, menu):
  if os.path.basename(path) in ("page!footer", "page!internet-explorer", "page!contribute-old"):
    return

  if os.path.basename(path).startswith("page!"):
    process_page(path, menu)
  elif os.path.basename(path).startswith("image!"):
    process_image(path)
  else:
    print >>sys.stderr, "Ignoring file %s" % path

def process(path, menu):
  if os.path.isfile(path):
    process_file(path, menu)
  elif os.path.isdir(path):
    for filename in os.listdir(path):
      process(os.path.join(path, filename), menu)
  else:
    print >>sys.stderr, "Ignoring file %s" % path

def process_menu():
  menu = {}

  menu_format = "%s/_include/menu!menu"
  footer_format = "%s/_include/page!footer"
  for locale in locales:
    menu[locale] = OrderedDict()
    if os.path.exists(menu_format % locale):
      data = read_xml(menu_format % locale)
      items = get_element(data.documentElement, "items")
      for node in items.childNodes:
        text = get_text(get_element(node, "mainlink", "anwv", "title", "anwv")).strip()
        url = get_text(get_element(node, "mainlink", "anwv", "url", "anwv")).strip()
        if url == "en":
          string = "installation"
        elif url.startswith("en/"):
          string = url.replace("en/", "")
        elif url == "/languages/":
          continue    # Unused string
        elif url == "/search/":
          string = "search"
        else:
          raise Exception("Unexpected URL in menu: %s" % url)
        if text and text.find("[untr]") < 0:
          menu[locale][string] = {"message": text}
    if os.path.exists(footer_format % locale):
      data = read_xml(footer_format % locale)
      for string, heading in itertools.izip(("resources", "community", "development", "follow-us"), data.getElementsByTagName("h1")):
        text = get_text(heading).strip()
        if text and text.find("[untr]") < 0:
          menu[locale][string] = {"message": text}
      for link in data.getElementsByTagName("a"):
        url = link.getAttribute("href").replace("/de/", "")
        text = get_text(link).strip()
        if url == "/forum/viewforum.php?f=11":
          string = "_bugs"
        elif url.startswith("/"):
          string = url.strip("/").split("/")[-1]
        elif url == "https://issues.adblockplus.org/report/13":
          string = "roadmap"
        else:
          string = url
        if text and text.find("[untr]") < 0:
          menu[locale][string] = {"message": text}
  return menu

os.chdir(input_dir)
menu = process_menu()
process("page!en", menu)
process("en", menu)
process("images", menu)

for locale, value in menu.iteritems():
  if "_bugs" in value:
    value["bugs"] = value["_bugs"]
    del value["_bugs"]
  localefile = os.path.join(output_dir, "locales", locale, "menu.json")
  save_locale(localefile, value)
