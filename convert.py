#!/usr/bin/env python
# coding: utf-8

import HTMLParser, codecs, errno, itertools, json, os, re, sys
from collections import OrderedDict
from xml.dom import minidom, Node

h = HTMLParser.HTMLParser()

output_dir = "../web.adblockplus.org"
input_dir = "../www"
locales = ("ar", "bg", "de", "en", "es", "fr", "he", "hu", "ko", "lt", "nl",
           "pt_BR", "ru", "sk", "zh_CN", "zh_TW")
entities = {"euro": 8364, "mdash": 8212, "nbsp": 0xA0, "copy": 169}

license_header = """{#
 # This file is part of the Adblock Plus website,
 # Copyright (C) 2006-2015 Eyeo GmbH
 #
 # Adblock Plus is free software: you can redistribute it and/or modify
 # it under the terms of the GNU General Public License version 3 as
 # published by the Free Software Foundation.
 #
 # Adblock Plus is distributed in the hope that it will be useful,
 # but WITHOUT ANY WARRANTY; without even the implied warranty of
 # MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 # GNU General Public License for more details.
 #
 # You should have received a copy of the GNU General Public License
 # along with Adblock Plus.  If not, see <http://www.gnu.org/licenses/>.
 #}"""

string_regexp = (
  r"{{\s*"
  r"([\w\-]+)" # String ID
  r"(?:\[(.*?)\])?" # Optional comment
  r"\s+"
  r"((?:(?!{{).|" # Translatable text
    r"{{(?:(?!}}).)*}}" # Nested translation
  r")*?)"
  r"}}"
)

class AttributeParser(HTMLParser.HTMLParser):
  _string = None
  _attrs = None

  def __init__(self, whitelist):
    self._whitelist = whitelist

  def parse(self, text, pagename):
    self.reset()
    self._string = []
    self._attrs = {}
    self._pagename = pagename

    try:
      self.feed(text)
      return "".join(self._string), self._attrs
    finally:
      self._string = None
      self._attrs = None
      self._pagename = None

  def handle_starttag(self, tag, attrs):
    if tag not in self._whitelist:
      raise Exception("Unexpected HTML tag '%s' in localizable string on page %s" % (tag, self._pagename))
    self._attrs.setdefault(tag, []).append(attrs)
    self._string.append("<%s>" % tag)

  def handle_endtag(self, tag):
    self._string.append("</%s>" % tag)

  def handle_data(self, data):
    # Note: lack of escaping here is intentional. The result is a locale string,
    # HTML escaping is applied when this string is inserted into the document.
    self._string.append(data)

  def handle_entityref(self, name):
    self._string.append(self.unescape("&%s;" % name))

  def handle_charref(self, name):
    self._string.append(self.unescape("&#%s;" % name))

tag_whitelist = {"a", "strong", "em", "code"}
attribute_parser = AttributeParser(tag_whitelist)

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

def extract_string(strings, property, *element_selector):
  element = get_element(*element_selector) if len(element_selector) > 1 else element_selector[0]
  text = get_text(element).strip()
  if text and "[untr]" not in text:
    strings[property] = {"message": text}

def squash_attrs(node):
  if node.nodeType == Node.ELEMENT_NODE:
    for child in list(node.childNodes):
      if child.nodeType == Node.ELEMENT_NODE and child.tagName == "attr":
        node.setAttribute(child.getAttribute("name"), get_text(child))
        node.removeChild(child)
  return node

def merge_children(nodes):
  def is_fixed(node):
    return (node.nodeType == Node.ELEMENT_NODE and
        node.tagName == "fix" and
        len(node.childNodes) and
        all(n.nodeType == Node.TEXT_NODE for n in node.childNodes) and
        any(re.search(r"[\w@]+", n.nodeValue) for n in node.childNodes))

  def is_text(node):
    if node.nodeType == Node.TEXT_NODE or is_fixed(node):
      return True
    if (node.nodeType == Node.ELEMENT_NODE and
        node.tagName in tag_whitelist and
        all(n.nodeType == Node.TEXT_NODE or is_fixed(n) for n in node.childNodes)):
      return True
    return False

  def is_empty(node):
    return node.nodeType == Node.TEXT_NODE and not node.nodeValue.strip()

  def serializeContents(nodes):
    result = []
    for node in nodes:
      if node.nodeType == Node.TEXT_NODE:
        result.append(node.nodeValue.replace("<", "&lt;").replace(">", "&gt;"))
      else:
        if node.childNodes:
          opening = node.cloneNode(False).toxml().replace("/>", ">")
          closing = re.sub(r"\s.*>", ">", opening).replace("<", "</")
          result.append(opening)
          result.append(serializeContents(node.childNodes))
          result.append(closing)
        else:
          result.append(node.toxml())

    return "".join(result)

  i = 0
  en = nodes["en"]
  if all(is_empty(n) or not is_text(n) or (n.nodeType == Node.ELEMENT_NODE and n.tagName == "a") for n in en.childNodes):
    return

  start = None
  i = 0
  while i <= len(en.childNodes):
    if start == None:
      if i < len(en.childNodes) and is_text(en.childNodes[i]):
        start = i
    elif i >= len(en.childNodes) or not is_text(en.childNodes[i]):
      end = i - 1
      while start < end and all(is_empty(node.childNodes[start]) for node in nodes.itervalues()):
        start += 1
      while start < end and all(is_empty(node.childNodes[end]) for node in nodes.itervalues()):
        end -= 1
      if start < end:
        for locale, parent in nodes.iteritems():
          if end < len(parent.childNodes):
            node = parent.ownerDocument.createTextNode(serializeContents(parent.childNodes[start:end+1]))
            parent.replaceChild(node, parent.childNodes[start])
            for child in parent.childNodes[start+1:end+1]:
              parent.removeChild(child)
          else:
            while start < len(parent.childNodes):
              parent.removeChild(parent.childNodes[start])
        i -= end - start
      start = None
    i += 1

def process_body(nodes, strings, prefix="", counter=1):
  if nodes["en"].nodeType == Node.ELEMENT_NODE:
    if nodes["en"].tagName not in ("style", "script", "fix", "pre"):
      for i in range(len(nodes["en"].childNodes)):
        node = nodes["en"].childNodes[i]
        if (node.nodeType == Node.ELEMENT_NODE and node.tagName == "a" and
            not node.hasAttribute("href") and get_element(node, "attr") and
            get_element(node, "attr").getAttribute("name") == "href"):
          # Process href attribute earlier for translatable links
          string_key = prefix + "s%i" % counter
          for locale, value in nodes.iteritems():
            attr = get_element(value.childNodes[i], "attr")
            text = get_text(attr).strip()
            attr.parentNode.setAttribute("href", "{{%s %s}}" % (string_key, text))
            attr.parentNode.removeChild(attr)
            if locale != "en" and "[untr]" not in text:
              strings[locale][string_key] = {"message": text}
          counter += 1

      merge_children(nodes)
      for i in range(len(nodes["en"].childNodes)):
        new_nodes = {}
        for locale, value in nodes.iteritems():
          if len(value.childNodes) > i:
            new_nodes[locale] = value.childNodes[i]
        counter = process_body(new_nodes, strings, prefix, counter)
    squash_attrs(nodes["en"])
  elif nodes["en"].nodeType == Node.TEXT_NODE:
    if any(n.nodeValue.strip() for n in nodes.itervalues()):
      message = nodes["en"].nodeValue.strip()
      message = re.sub(r'\s+--(?!>)', u'\u00A0\u2014', message)
      message = message.replace(u'\u00AB ', u'\u00AB\u00A0').replace(u' \u00BB', u'\u00A0\u00BB')
      string_key = prefix + "s%i" % counter

      for locale, value in nodes.iteritems():
        text = value.nodeValue or ""
        text = re.sub(r'\s+--(?!>)', u'\u00A0\u2014', text)
        text = text.replace(u'\u00AB ', u'\u00AB\u00A0').replace(u' \u00BB', u'\u00A0\u00BB')
        pre, text, post = re.search(r"^(\s*)(.*?)(\s*)$", text, re.S).groups()
        if string_key == prefix + "s%i" % counter and text and "[untr]" not in text:
          text = re.sub("\n\s+", " ", text, flags=re.S)
          if locale != "en":
            def replace_fixed(match):
              fixed_count[0] += 1
              return "{%d}" % fixed_count[0]

            fixed_count = [0]
            text = re.sub(r"<fix>.*?</fix>", replace_fixed, text, flags=re.S)
            text, _ = attribute_parser.parse(text, "")
            strings[locale][string_key] = {"message": text}
        value.nodeValue = "%s{{%s %s}}%s" % (pre, string_key, message + (" " if message.endswith("}") else ""), post)
      counter += 1
  elif nodes["en"].nodeType == Node.COMMENT_NODE:
    pass
  else:
    print >>sys.stderr, "Unexpected node type %i" % nodes["en"].nodeType

  return counter

def xml_to_text(xml, strings=None):
  def unescape(match):
    return '{{%s %s}}' % (match.group(1), h.unescape(match.group(3)))

  def rename_links(match):
    def rename_link(match):
      key, url = match.groups()
      new_key = parent_key + "-link" + (str(counter.value) if counter.value > 1 else "")
      counter.value += 1
      for locale, value in strings.iteritems():
        if key in value:
          value[new_key] = value[key]
          del value[key]
      return 'href="{{%s %s}}"' % (new_key, h.unescape(url))

    counter = lambda: None
    counter.value = 1
    parent_key = match.group(1)
    text = re.sub(r'href="{{(\S+) (\S+)}}"', rename_link, match.group(3))
    return '{{%s %s}}' % (parent_key, text)

  result = xml.toxml()

  if strings:
    # Merge duplicate strings
    candidates = {}
    def find_duplicates(match):
      key = match.group(1)
      text = re.sub(r"<fix>.*?</fix>", '{1}', h.unescape(match.group(3)), flags=re.S)
      text, _ = attribute_parser.parse(text, "")
      text = {"_default": text}
      for locale in strings.iterkeys():
        if key in strings[locale]:
          text[locale] = strings[locale][key]["message"]
      existing = [k for k, v in candidates.iteritems() if v == text]
      if existing and len(text["_default"]) >= 8:
        for locale in text.iterkeys():
          if locale != "_default":
            del strings[locale][key]
        return "{{%s %s}}" % (existing[0], match.group(3))
      else:
        candidates[key] = text
        return match.group(0)

    result = re.sub(string_regexp, find_duplicates, result, flags=re.S)

  result = re.sub(r"</?fix/?>", "", result, flags=re.S)

  result = re.sub(string_regexp, unescape, result, flags=re.S)
  if strings:
    result = re.sub(string_regexp, rename_links, result, flags=re.S)

  result = re.sub(r"</?anwv/?>", "", result)
  result = re.sub(r"</?notoc/?>", "", result)
  result = result.replace("/_override-static/global/global", "")

  # <script src=""/> => <script src=""></script>
  result = re.sub(r'<((?!link\b|meta\b|br\b|col\b|base\b|img\b|param\b|area\b|hr\b|input\b)([\w:]+)\b[^<>]*)/>', r'<\1></\2>', result, flags=re.S)

  # <img src="foo"/> => <img src="foo">
  result = re.sub(r'\/>', r'>', result)

  # <img src="foo">dummy</img> => <img src="foo">
  result = re.sub(r'<((link|meta|br|col|base|img|param|area|hr|input)\b[^<>]*)>([^<>]*)</\2>', r'<\1>', result, flags=re.S)

  def translate_tabs(tabstop = 8):
    offset = [0]
    def replace(match, offset=offset):
      offset[0] += match.start(0)
      return " " * (tabstop - offset[0] % tabstop)
    return replace

  # Remove some trailing whitespace and replace tabs with spaces
  result = "\n".join([re.sub(r'\t', translate_tabs(8), s) for s in result.split("\n")])
  result = re.sub(r'\ +\n', '\n', result, flags=re.S)

  return result

def raw_to_template(text):
  # {{s1 Hello World}} => {{"Hello World"|translate("s1")}}
  def escape_string(s):
    return s.replace("\\", "\\\\").replace('"', '\\"').replace("\r", "\\r").replace("\n", "\\n")
  def convert_translatable_strings(match):
    return '{{"%s"|translate("%s")}}' % (escape_string(h.unescape(match.group(3))), match.group(1))
  text = re.sub(string_regexp, convert_translatable_strings, text, flags=re.S)

  # <anwtoc page="en/android-faq" titletag="h2"></anwtoc> => {{toc("android-faq", "h2")}}
  def convert_toc(match):
    params = '", "'.join([m for m in match.groups() if not m is None])
    return '{{toc("%s")}}' % params
  text = re.sub(
    r'<anwtoc page="\w+/([\w-]+)"(?: titletag="([\w]+)")?></anwtoc>',
    convert_toc,
    text
  )

  return text

def move_meta_tags(head, body):
  meta_tag_regexp = r"<meta\b[^>]*>\s?"
  head += "".join(re.findall(meta_tag_regexp, body, re.I + re.S))
  return head, re.sub(meta_tag_regexp, "", body)

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

  for locale, value in data.iteritems():
    extract_string(strings[locale], "title", value.documentElement, "title", "anwv")

  variables = ["title=%s" % strings["en"]["title"]["message"]]
  del strings["en"]["title"]

  bodies = {}
  for locale, value in data.iteritems():
    bodies[locale] = get_element(value.documentElement, "body", "anwv")
  process_body(bodies, strings)

  body = xml_to_text(bodies["en"], strings)
  head = xml_to_text(get_element(data["en"].documentElement, "head", "anwv"), strings)
  head, body = move_meta_tags(head, body)

  if "<animation" in body and not "animation.js" in head:
    head += "\n<script src='/js/animation.js'></script>"

  head = re.sub(r'(src="/)((?:deregifier|redundancyCheck|webtools)\.js")', r'\1js/\2', head)
  head = re.sub(r'src="/FilterClasses.jsm"', r'src="/js/filterClasses.js"', head)
  head = re.sub(r'(url\(&quot;/)((?:facebook|twitter|googleplus)\.png&quot;\))', r'\1img/\2', head)

  if head:
    pagedata = "<head>%s</head>%s" % (h.unescape(head), body)
  else:
    pagedata = body

  contains_toc = "<anwtoc" in pagedata

  if pagename == "index":
    pagedata = license_header + "\n\n" + raw_to_template(pagedata)
    variables.append("noheading=True")
    variables.append("localefile=index")
  elif contains_toc:
    pagedata = (license_header + '\n\n{% from "includes/toc" import toc %}\n\n' +
                raw_to_template(pagedata))
  elif pagename in ("acceptable-ads-manifesto", "share", "customize-youtube", "customize-facebook"):
    variables.append("template=minimal")

  pagedata = "\n".join(variables) + "\n\n" + pagedata

  if pagename == "index":
    target = os.path.join(output_dir, "includes", pagename + ".tmpl")
  elif contains_toc:
    target = os.path.join(output_dir, "pages", pagename + ".tmpl")
  else:
    target = os.path.join(output_dir, "pages", pagename + ".html")
  ensure_dir(target)
  with codecs.open(target, "wb", encoding="utf-8") as handle:
    handle.write(pagedata)

  for locale, value in strings.iteritems():
    if value:
      localefile = os.path.join(output_dir, "locales", locale, pagename + ".json")
      save_locale(localefile, value)

def process_image(path):
  if path.split("/")[0] in locales:
    target = os.path.join(output_dir, "locales", os.path.dirname(path), os.path.basename(path).replace("image!", ""))
  else:
    target = os.path.join(output_dir, "static", os.path.dirname(path), os.path.basename(path).replace("image!", ""))
  with open(path, "rb") as handle:
    data = handle.read()

  ensure_dir(target)
  with open(target, "wb") as handle:
    handle.write(data)

  if path.startswith("en/"):
    for locale in locales:
      if locale == "en":
        continue
      new_path = locale + path[2:]
      if os.path.exists(new_path):
        process_image(new_path)

def process_interface(path):
  pagename = os.path.join(os.path.dirname(path), os.path.basename(path).replace("interface!", ""))
  format = "%s/" + path.split("/", 1)[1]
  pagename = pagename.split("/", 1)[1]

  data = {}
  strings = {}

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

    interface[property_key] = OrderedDict({
      "description": "$%sDescription$" % property_name
    })

  for method in get_element(data["en"].documentElement, "methods").childNodes:
    method_name = get_text(get_element(method, "name", "anwv")).strip()
    method_return_type = get_text(get_element(method, "return_type", "anwv")).strip()
    method_version = get_text(get_element(method, "version", "anwv")).strip()
    argument_string = ""
    argument_names = []
    for argument in get_element(method, "arguments").childNodes:
      argument_name = get_text(get_element(argument, "name", "anwv")).strip()
      argument_type = get_text(get_element(argument, "type", "anwv")).strip()
      argument_string += " %s %s," % (argument_type, argument_name)
      argument_names.append(argument_name)
    argument_string = argument_string.strip().strip(",")
    method_key = "%s %s(%s)" % (method_return_type, method_name, argument_string)

    interface[method_key] = OrderedDict({
      "description": "$%sDescription$" % method_name
    })
    for argument_name in argument_names:
      interface[method_key]["description-%s" % argument_name] = "$%s_%sDescription$" % (method_name, argument_name)
    if method_return_type != "void":
      interface[method_key]["description-return"] = "$%s_returnDescription$" % method_name
    if method_version:
      interface[method_key]["version"] = method_version

  # ... and sort them by their names
  interface = OrderedDict(sorted(interface.iteritems(), key=lambda x: x[0].split("(")[0].strip().split()[-1]))

  descriptions = OrderedDict()
  for locale, value in data.iteritems():
    def set_description(key, element):
      if not key in descriptions:
        descriptions[key] = {}
      descriptions[key][locale] = element

    extract_string(strings[locale], "title", value.documentElement, "title", "anwv")

    # Store the description blocks
    set_description("", get_element(value.documentElement, "description", "anwv"))

    # Find all the translations for property, method and method argument descriptions
    for property in get_element(value.documentElement, "properties").childNodes:
      property_name = get_text(get_element(property, "name", "anwv")).strip()
      set_description(property_name + "Description",
          get_element(property, "description", "anwv"))
    for method in get_element(value.documentElement, "methods").childNodes:
      method_name = get_text(get_element(method, "name", "anwv")).strip()
      set_description(method_name + "Description",
          get_element(method, "description", "anwv"))
      set_description(method_name + "_returnDescription",
          get_element(method, "return_description", "anwv"))
      for argument in get_element(method, "arguments").childNodes:
        argument_name = get_text(get_element(argument, "name", "anwv")).strip()
        set_description(method_name + "_" + argument_name + "Description",
            get_element(argument, "description", "anwv"))

  # Translate the strings in the descriptions
  for key in descriptions:
    process_body(descriptions[key], strings, key + "-" if key else "")

  # Write general interface strings to the interface.json locale file
  localefile = os.path.join(output_dir, "locales", "en", "interface.json")
  save_locale(localefile, OrderedDict([
    ("general_notes", { "message": "General notes" }),
    ("toc_header", {"message": "Methods and properties" }),
    ("minversion_label", {"message": "Version:" }),
    ("minversion_addendum", {"message": "and higher" }),
    ("arguments_label", {"message": "Arguments:" }),
    ("returnvalue_label", {"message": "Returns:" })
  ]))

  pagedata = ""
  for key, value in descriptions.iteritems():
    if key:
      pagedata += "{%% macro %s() %%}\n" % key
    pagedata += raw_to_template(xml_to_text(value["en"], strings)).lstrip()
    if key:
      pagedata += "{% endmacro %}\n"
    pagedata += "\n"

  pagedata = """title=%s

%s

%s

%s
{#
  Property, method and method argument descriptions are defined in the macros
  above and only referenced here.
#}

{%% from "includes/interface" import display_interface %%}

{{ display_interface(%s) }}
""" % (
    strings["en"]["title"]["message"],
    license_header,
    '<h2>{{ get_string("general_notes", "interface") }}</h2>',
    pagedata,
    re.sub(r'"\$.*?\$"', lambda match: json.loads(match.group(0))[1:-1], json.dumps(interface, indent=2, separators=(',', ': ')))
  )
  del strings["en"]["title"]

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
    new_section = OrderedDict(id=section_id)
    title = get_text(get_element(section, "title", "anwv")).strip()
    new_section["title"] = "$'%s'|translate('%sTitle')$" % (title.replace("'", "\\'"), section_id)
    new_section["preferences"] = []

    for preference in get_element(section, "preferences").childNodes:
      preference_name = get_text(get_element(preference, "name", "anwv")).strip()
      new_preference = OrderedDict(name=preference_name)
      new_preference["default"] = get_text(get_element(preference, "default", "anwv")).strip()
      if get_text(get_element(preference, "empty", "anwv")).strip() == "true":
        new_preference["default"] = "$None$"
      new_preference["description"] = "$%sDescription$" % re.sub(r'\W', '', preference_name)
      new_section["preferences"].append(new_preference)
    new_section["preferences"].sort(key=lambda p: p["name"])
    sections.append(new_section)

  descriptions = OrderedDict()
  for locale, value in data.iteritems():
    def set_description(key, element):
      if not key in descriptions:
        descriptions[key] = {}
      descriptions[key][locale] = element

    extract_string(strings[locale], "title", value.documentElement, "title", "anwv")

    set_description("", get_element(value.documentElement, "description", "anwv"))

    if locale != "en":
      extract_string(strings[locale], "prefnamecol", value.documentElement, "prefnamecol", "anwv")
      extract_string(strings[locale], "defaultcol", value.documentElement, "defaultcol", "anwv")
      extract_string(strings[locale], "descriptioncol", value.documentElement, "descriptioncol", "anwv")
      extract_string(strings[locale], "empty", value.documentElement, "emptydefault", "anwv")

    for section in get_element(value.documentElement, "sections").childNodes:
      section_id = get_text(get_element(section, "id", "anwv")).strip()
      if locale != "en":
        extract_string(strings[locale], section_id + "Title", section, "title", "anwv")
      for preference in get_element(section, "preferences").childNodes:
        preference_name = get_text(get_element(preference, "name", "anwv")).strip()
        set_description(preference_name, get_element(preference, "description", "anwv"))

  # Translate the strings in the descriptions
  for key in descriptions:
    process_body(descriptions[key], strings, re.sub(r'\W', '', key) + "-" if key else "")

  pagedata = ""
  for key, value in descriptions.iteritems():
    if key:
      pagedata += "{%% macro %sDescription() %%}\n" % re.sub(r'\W', '', key)
    pagedata += raw_to_template(xml_to_text(value["en"], strings)).lstrip()
    if key:
      pagedata += "{% endmacro %}\n"
    pagedata += "\n"

  pagedata = """title=%s

%s

%s
{#
  Preference descriptions are defined in the macros above and only referenced
  here.
#}

{%% from "includes/preftable" import display_preftable %%}

{{ display_preftable(%s) }}
""" % (
    strings["en"]["title"]["message"],
    license_header,
    pagedata,
    re.sub(r'"\$.*?\$"', lambda match: json.loads(match.group(0))[1:-1], json.dumps(sections, indent=2, separators=(',', ': ')))
  )
  del strings["en"]["title"]

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
    extract_string(strings[locale], "title", value.documentElement, "title", "anwv")

    headers[locale] = get_element(value.documentElement, "header", "anwv")
    footers[locale] = get_element(value.documentElement, "footer", "anwv")

    for subst in get_element(value.documentElement, "subst").childNodes:
      subst_name = get_text(get_element(subst, "name", "anwv")).strip()
      if subst_name.startswith("type_") or locale != "en":
        extract_string(strings[locale], subst_name, subst, "text", "anwv")

  # Prepare the header and footer
  process_body(footers, strings, counter=process_body(headers, strings))

  pagedata = ("""title=%s
%s

%s

{%% from "includes/subscriptionList" import display_subscriptions %%}

{{ display_subscriptions(1|get_subscriptions) }}

%s""") % (
    strings["en"]["title"]["message"],
    license_header,
    raw_to_template(xml_to_text(headers["en"], strings)),
    raw_to_template(xml_to_text(footers["en"], strings))
  )
  del strings["en"]["title"]

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

def process_animation(path):
  animation_name = os.path.basename(path).replace("animation!anim_", "").replace(".xml", "")
  animation_xml = read_xml(path)

  width = get_text(get_element(animation_xml.documentElement, "width", "anwv")).strip()
  height = get_text(get_element(animation_xml.documentElement, "height", "anwv")).strip()
  animation_data = get_element(animation_xml.documentElement, "data", "anwv")

  animation_data.tagName = "animation"
  animation_data.setAttribute("xmlns", "https://adblockplus.org/animation")
  animation_data.setAttribute("width", width)
  animation_data.setAttribute("height", height)

  for child in animation_data.childNodes:
    if (child.nodeType == Node.ELEMENT_NODE and
        child.tagName == "object" and
        child.hasAttribute("src")):
      child.setAttribute("src", "{{'%s'|inline_file}}" % child.getAttribute("src"))

  page_data = "template=raw\n\n" + xml_to_text(animation_data) + "\n"
  target = os.path.join(output_dir, "pages", "animations", animation_name + ".xml.tmpl")
  ensure_dir(target)
  with codecs.open(target, "wb", encoding="utf-8") as handle:
    handle.write(page_data)

def process_file(path, menu):
  if os.path.basename(path) in ("page!footer", "page!internet-explorer"):
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
  elif os.path.basename(path).startswith("animation!"):
    process_animation(path)
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
        extract_string(menu[locale], string, heading)
      for link in data.getElementsByTagName("a"):
        url = link.getAttribute("href").replace("/de/", "")
        if url == "/forum/viewforum.php?f=11":
          string = "_bugs"
        elif url.startswith("/"):
          string = url.strip("/").split("/")[-1]
        elif url == "https://issues.adblockplus.org/report/13":
          string = "roadmap"
        else:
          string = url
        extract_string(menu[locale], string, link)
  return menu

if __name__ == "__main__":
  os.chdir(input_dir)
  menu = process_menu()
  process("page!en", menu)
  process("en", menu)
  process("images", menu)
  process("_include", menu)

  for locale, value in menu.iteritems():
    if "_bugs" in value:
      value["bugs"] = value["_bugs"]
      del value["_bugs"]
    localefile = os.path.join(output_dir, "locales", locale, "menu.json")
    save_locale(localefile, value)
