#!/usr/bin/env python
# coding: utf-8

import HTMLParser, codecs, errno, itertools, json, os, re, sys
from collections import OrderedDict
from xml.dom import minidom, Node

h = HTMLParser.HTMLParser()

output_dir = "../wwwnew"
input_dir = "../www"
locales = ("ar", "bg", "de", "en", "es", "fr", "he", "hu", "ko", "lt", "nl",
           "pt_BR", "ru", "sk", "zh_CN", "zh_TW")
entities = {"euro": 8364, "mdash": 8212, "nbsp": 0xA0, "copy": 169}

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
    return minidom.parseString("<!DOCTYPE root [%s]><root>%s</root>" % (
      "".join(["<!ENTITY %s \"&#%d;\">" % (k, v) for k,v in entities.iteritems()]),
      xml
    ))

def save_locale(path, data):
  ensure_dir(path)
  with codecs.open(path, "wb", encoding="utf-8") as handle:
    json.dump(data, handle, ensure_ascii=False, indent=2, separators=(',', ': '))

def get_text(node):
  result = []
  for child in node.childNodes:
    if child.nodeType != Node.TEXT_NODE:
      print child.tagName
      raise Exception("Unexpected node type %s." % [
        "ELEMENT_NODE", "ATTRIBUTE_NODE", "TEXT_NODE", "CDATA_SECTION_NODE",
        "ENTITY_REFERENCE_NODE", "ENTITY_NODE", "PROCESSING_INSTRUCTION_NODE",
        "COMMENT_NODE", "DOCUMENT_NODE", "DOCUMENT_TYPE_NODE",
        "DOCUMENT_FRAGMENT_NODE", "NOTATION_NODE"
      ][child.nodeType])

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

def squash_attrs(node):
  if node.nodeType == Node.ELEMENT_NODE:
    for child in node.childNodes:
      if child.nodeType == Node.ELEMENT_NODE and child.tagName == "attr":
        node.setAttribute(child.getAttribute("name"), get_text(child))
        node.removeChild(child)
  return node

def smart_strip(s):
  return (" " if re.search(r"^\s", s) else "") + s.strip() + (" " if re.search(r"\s$", s) else "")

def get_descriptions(strings, links, locale, node, key_name, tag_name="description"):
  def get_paragraphs(nodes, current_paragraph=""):
    if len(nodes):
      if nodes[0].nodeType == Node.TEXT_NODE:
        current_paragraph += smart_strip(nodes[0].nodeValue)
      elif nodes[0].nodeType == Node.ELEMENT_NODE:
        nodes[0] = squash_attrs(nodes[0])
        if nodes[0].tagName in ["strong", "em", "tt", "code"]:
          current_paragraph += smart_strip(re.sub(r"(\<(\/?)(code|tt|sub|a[^\>]*)\>)+", r"<\2strong>", nodes[0].toxml()))
        elif nodes[0].tagName == "a":
          current_paragraph += smart_strip(nodes[0].toxml())
        else:
          return [current_paragraph.strip()] + get_paragraphs(nodes[0].childNodes + nodes[1:])
      if (len(nodes) == 1):
        return [current_paragraph.strip()]
      else:
        return get_paragraphs(nodes[1:], current_paragraph)
    else:
      return [current_paragraph.strip()]

  i = 0
  for paragraph in get_paragraphs(get_element(node, tag_name, "anwv").childNodes):
    if paragraph:
      if locale == "en":
        paragraph_links = re.findall(r"href\s*=\s*['\"]([^'\"]+)['\"]", paragraph)
        if paragraph_links:
          links["%sDescription%s" % (key_name, i and str(i) or "")] = paragraph_links
          paragraph = re.sub(r"<a[^>]+>", "<a>", paragraph)
      paragraph = re.sub(r"\<(\/?)a\>", r"<\1a>", paragraph)
      if paragraph.find("[untr]") < 0:
        strings[locale]["%sDescription%s" % (key_name, i and str(i) or "")] = {
          "message": paragraph
        }
      i += 1
  return i

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
                child = squash_attrs(child)
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

def process_body(nodes, strings, value_format="%s$%s%s$%s", counter=1):
  if nodes["en"].nodeType == Node.ELEMENT_NODE:
    if nodes["en"].tagName not in ("style", "script", "fix", "pre"):
      merge_children(nodes)
      for i in range(len(nodes["en"].childNodes)):
        new_nodes = {}
        for locale, value in nodes.iteritems():
          if len(value.childNodes) > i:
            new_nodes[locale] = value.childNodes[i]
        counter = process_body(new_nodes, strings, value_format, counter)
  elif nodes["en"].nodeType == Node.TEXT_NODE:
    if nodes["en"].nodeValue.strip():
      if hasattr(nodes["en"], "links") and len(nodes["en"].links):
        if value_format.find("translate") > -1:
          links = "['%s']" % "', '".join(nodes["en"].links)
        else:
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
        value.nodeValue = value_format % (pre, string_key, links, post)
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
    pagedata = "<head>%s</head>%s" % (h.unescape(head), body)
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
  elif pagename == "acceptable-ads-manifesto":
    pagedata = "template=minimal\n\n%s" % pagedata

  if pagename != "index" and titlestring != "title":
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
  elif path.startswith("images/manifesto/") and not "background" in path:
    target = os.path.join(output_dir, "locales", "en", os.path.dirname(path), os.path.basename(path).replace("image!", ""))
  else:
    target = os.path.join(output_dir, "static", os.path.dirname(path), os.path.basename(path).replace("image!", ""))
  with open(path, "rb") as handle:
    data = handle.read()

  ensure_dir(target)
  with open(target, "wb") as handle:
    handle.write(data)

def process_interface(path):
  pagename = os.path.join(os.path.dirname(path), os.path.basename(path).replace("interface!", ""))
  format = "%s/" + path.split("/", 1)[1]
  pagename = pagename.split("/", 1)[1]

  data = {}
  strings = {}
  descriptions = {}

  for locale in locales:
    if not os.path.exists(format % locale):
      continue
    data[locale] = read_xml(format % locale)
    strings[locale] = OrderedDict()

  # Store the methods and properties for the interface
  interface = {}

  for property in get_element(data["en"].documentElement, "properties").childNodes:
    property_name = get_text(get_element(property, "name", "anwv")).strip()
    property_type = get_text(get_element(property, "type", "anwv")).strip()
    property_modifier = get_text(get_element(property, "modifier", "anwv")).strip()
    property_key = " ".join([property_modifier, property_type, property_name]).strip()
    interface[property_key] = None

  for method in get_element(data["en"].documentElement, "methods").childNodes:
    method_name = get_text(get_element(method, "name", "anwv")).strip()
    method_return_type = get_text(get_element(method, "return_type", "anwv")).strip()
    method_version = get_text(get_element(method, "version", "anwv")).strip()
    argument_string = ""
    for argument in get_element(method, "arguments").childNodes:
      argument_name = get_text(get_element(argument, "name", "anwv")).strip()
      argument_type = get_text(get_element(argument, "type", "anwv")).strip()
      argument_string += " %s %s," % (argument_type, argument_name)
    argument_string = argument_string.strip().strip(",")
    method_key = "%s %s(%s)" % (method_return_type, method_name, argument_string)
    interface[method_key] = {
      "version": method_version
    }
    # ... and sort them by their names
    interface = OrderedDict(sorted(interface.iteritems(), key=lambda x: x[0].split("(")[0].strip().split()[-1]))

  links = {}

  for locale, value in data.iteritems():
    title = get_text(get_element(data[locale].documentElement, "title", "anwv")).strip()
    if title and title.find("[untr]") < 0:
      strings[locale]["title"] = {"message": title}

    # Store the description blocks
    descriptions[locale] = get_element(value.documentElement, "description", "anwv")

    # Find all the translations for property, method and method argument descriptions
    for property in get_element(value.documentElement, "properties").childNodes:
      property_name = get_text(get_element(property, "name", "anwv")).strip()
      get_descriptions(strings, links, locale, property, property_name)
    for method in get_element(value.documentElement, "methods").childNodes:
      method_name = get_text(get_element(method, "name", "anwv")).strip()
      get_descriptions(strings, links, locale, method, method_name)
      get_descriptions(strings, links, locale, method, method_name +
                       "-return", "return_description")
      for argument in get_element(method, "arguments").childNodes:
        argument_name = get_text(get_element(argument, "name", "anwv")).strip()
        get_descriptions(strings, links, locale, argument, method_name +
                         "-" + argument_name)

  # Translate the strings in the description
  process_body(descriptions, strings, "%s{{ '%s'|translate(None, %s) }}%s")

  strings["en"]["general_notes"] = { "message": "General notes" }
  strings["en"]["toc_header"] = {"message": "Methods and properties" }

  description_comment = ("\n\n{#\nProperty, method and method argument descriptions live in the locale files.\n" +
                         "The convention is propertynameDescription, methodnameDescription methodname-returnDescription\n" +
                         "and methodname-argumentnameDescription. If you need more than one paragraph append\n" +
                         "a number starting at one, for example nameDescription1 for the second paragraph.\n" +
                         "If you need to add links to a description add a links dictionary that contains an array of link\n"
                         "strings for the description key, for example {\"propertynameDescription\": [\"http://google.com\"]} #}\n\n")

  pagedata = re.sub(r"</?anwv/?>", "", descriptions["en"].toxml())
  pagedata = "%s%s\n\n%s{%% from \"includes/interface\" import display_interface with context %%}\n\n{{ display_interface(%s, %s) }}" % (
    '<h2>{{ "general_notes"|translate }}</h2>',
    pagedata,
    description_comment,
    json.dumps(interface, indent=2, separators=(',', ': ')),
    json.dumps(links, indent=2, separators=(',', ': '))
  )

  # Save the page's HTML
  target = os.path.join(output_dir, "pages", pagename + ".tmpl")
  ensure_dir(target)
  with codecs.open(target, "wb", encoding="utf-8") as handle:
    handle.write(pagedata)
  # Save all the translations of strings for the page
  for locale, value in strings.iteritems():
    if value:
      localefile = os.path.join(output_dir, "locales", locale, pagename + ".json")
      save_locale(localefile, value)

def process_preftable(path):
  pagename = os.path.join(os.path.dirname(path), os.path.basename(path).replace("preftable!", ""))
  format = "%s/" + path.split("/", 1)[1]
  pagename = pagename.split("/", 1)[1]

  data = {}
  strings = {}
  descriptions = {}
  tables = {}

  for locale in locales:
    if not os.path.exists(format % locale):
      continue
    data[locale] = read_xml(format % locale)
    strings[locale] = OrderedDict()
    tables[locale] = []

  # Table sections
  sections = []
  for section in get_element(data["en"].documentElement, "sections").childNodes:
    section_id = get_text(get_element(section, "id", "anwv")).strip()
    new_section = {
      "id": section_id,
      "preferences": []
    }
    for preference in get_element(section, "preferences").childNodes:
      preference_name = get_text(get_element(preference, "name", "anwv")).strip()
      new_preference = {
        "name": preference_name,
        "default": get_text(get_element(preference, "default", "anwv")).strip()
      }
      if get_text(get_element(preference, "empty", "anwv")).strip() == "true":
        new_preference["default"] = None
      new_section["preferences"].append(new_preference)
    new_section["preferences"].sort(key=lambda p: p["name"])
    sections.append(new_section)

  links = {}

  for locale, value in data.iteritems():
    title = get_text(get_element(data[locale].documentElement, "title", "anwv")).strip()
    if title and title.find("[untr]") < 0:
      strings[locale]["title"] = {"message": title}

    descriptions[locale] = get_element(value.documentElement, "description", "anwv")

    prefnamecol = get_text(get_element(value.documentElement, "prefnamecol", "anwv")).strip()
    if prefnamecol and prefnamecol.find("[untr]") < 0:
      strings[locale]["prefnamecol"] = { "message": prefnamecol }
    defaultcol = get_text(get_element(value.documentElement, "defaultcol", "anwv")).strip()
    if defaultcol and prefnamecol.find("[untr]") < 0:
      strings[locale]["defaultcol"] = { "message": defaultcol }
    descriptioncol = get_text(get_element(value.documentElement, "descriptioncol", "anwv")).strip()
    if descriptioncol and descriptioncol.find("[untr]") < 0:
      strings[locale]["descriptioncol"] = { "message": descriptioncol }

      for section in get_element(value.documentElement, "sections").childNodes:
        section_id = get_text(get_element(section, "id", "anwv")).strip()
        section_title = get_text(get_element(section, "title", "anwv")).strip()
        if section_title and section_title.find("[untr]") < 0:
          strings[locale][section_id + "Title"] = { "message": section_title }
        for preference in get_element(section, "preferences").childNodes:
          preference_name = get_text(get_element(preference, "name", "anwv")).strip()
          get_descriptions(strings, links, locale, preference, preference_name)

  process_body(descriptions, strings, "%s{{ '%s'|translate(None, %s) }}%s")

  pagedata = re.sub(r"</?anwv/?>", "", descriptions["en"].toxml())
  pagedata = "%s\n\n{%% from \"includes/preftable\" import display_preftable with context %%}\n\n{{ display_preftable(%s, %s) }}" % (
    pagedata,
    json.dumps(sections, indent=2, separators=(',', ': ')),
    json.dumps(links, indent=2, separators=(',', ': '))
  )

  # Save the page's HTML
  target = os.path.join(output_dir, "pages", pagename + ".tmpl")
  ensure_dir(target)
  with codecs.open(target, "wb", encoding="utf-8") as handle:
    handle.write(pagedata)
  # Save all the translations of strings for the page
  for locale, value in strings.iteritems():
    if value:
      localefile = os.path.join(output_dir, "locales", locale, pagename + ".json")
      save_locale(localefile, value)

def process_subscriptionlist(path):
  pagename = os.path.join(os.path.dirname(path), os.path.basename(path).replace("subscriptionlist!", ""))
  format = "%s/" + path.split("/", 1)[1]
  pagename = pagename.split("/", 1)[1]

  data = {}
  strings = {}
  headers = {}
  footers = {}
  tables = {}

  for locale in locales:
    if not os.path.exists(format % locale):
      continue
    data[locale] = read_xml(format % locale)
    strings[locale] = OrderedDict()
    tables[locale] = []

  for locale, value in data.iteritems():
    title = get_text(get_element(data[locale].documentElement, "title", "anwv")).strip()
    if title and title.find("[untr]") < 0:
      strings[locale]["title"] = {"message": title}

    headers[locale] = get_element(value.documentElement, "header", "anwv")
    footers[locale] = get_element(value.documentElement, "footer", "anwv")

    for subst in get_element(value.documentElement, "subst").childNodes:
      subst_name = get_text(get_element(subst, "name").firstChild).strip()
      subst_value = get_text(get_element(subst, "text").firstChild).strip()
      if subst_name and subst_value and subst_value.find("[untr]") < 0:
        strings[locale][subst_name] = { "message": subst_value }

  # Prepare the header and footer
  process_body(footers, strings, "%s{{ '%s'|translate(None, %s) }}%s",
               process_body(headers, strings, "%s{{ '%s'|translate(None, %s) }}%s"))

  strings["en"]["maintainer_suffix"] = {"message": ""}
  strings["en"]["supplements_suffix"] = {"message": ""}

  pagedata = ("%s\n\n{%% from \"includes/subscriptionList\" import display_subscriptions with context %%}\n{{ display_subscriptions(1|get_subscriptions) }}\n\n%s") % (
    headers["en"].toxml(), footers["en"].toxml()
  )

  # Save the page's HTML
  target = os.path.join(output_dir, "pages", pagename + ".tmpl")
  ensure_dir(target)
  with codecs.open(target, "wb", encoding="utf-8") as handle:
    handle.write(pagedata)
  # Save all the translations of strings for the page
  for locale, value in strings.iteritems():
    if value:
      localefile = os.path.join(output_dir, "locales", locale, pagename + ".json")
      save_locale(localefile, value)

def process_file(path, menu):
  if os.path.basename(path) in ("page!footer", "page!internet-explorer", "page!contribute-old"):
    return

  if os.path.basename(path).startswith("page!"):
    process_page(path, menu)
  elif os.path.basename(path).startswith("image!"):
    process_image(path)
  elif os.path.basename(path).startswith("interface!"):
    process_interface(path)
  elif os.path.basename(path).startswith("preftable!"):
    process_preftable(path)
  elif os.path.basename(path).startswith("subscriptionlist!"):
    process_subscriptionlist(path)
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

if __name__ == "__main__":
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
