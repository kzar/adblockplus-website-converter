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
    if nodes["en"].tagName not in ("style", "script", "fix", "pre"):
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
  interface = {
    "properties": {},
    "methods": {}
  }
  for property in get_element(data["en"].documentElement, "properties").childNodes:
    property_name = get_text(get_element(property, "name", "anwv")).strip()
    property_type = get_text(get_element(property, "type", "anwv")).strip()
    property_modifier = get_text(get_element(property, "modifier", "anwv")).strip()
    property_description = "$%sDescription$" % property_name
    interface["properties"][property_name] = {
      "name": property_name,
      "type": property_type,
      "modifier": property_modifier,
      "description": property_description
    }
  for method in get_element(data["en"].documentElement, "methods").childNodes:
    method_name = get_text(get_element(method, "name", "anwv")).strip()
    method_return_type = get_text(get_element(method, "return_type", "anwv")).strip()
    method_return_description = "$%sReturnDescription$" % method_name
    method_description = "$%sDescription$" % method_name
    method_version = get_text(get_element(method, "version", "anwv")).strip()
    method_arguments = []
    for argument in get_element(method, "arguments").childNodes:
      argument_name = get_text(get_element(argument, "name", "anwv")).strip()
      argument_type = get_text(get_element(argument, "type", "anwv")).strip()
      argument_description = "$%sArgument%sDescription$" % (method_name, argument_name)

      method_arguments.append({
        "name": argument_name,
        "type": argument_type,
        "description": argument_description
      })
    interface["methods"][method_name] = {
      "name": method_name,
      "return_type": method_return_type,
      "return_description": method_return_description,
      "description": method_description,
      "version": method_version,
      "arguments": method_arguments
    }

  for locale, value in data.iteritems():
    title = get_text(get_element(data[locale].documentElement, "title", "anwv")).strip()
    if title and title.find("[untr]") < 0:
      strings[locale]["title"] = {"message": title}

    # Store the description blocks
    descriptions[locale] = get_element(value.documentElement, "description", "anwv")

    # Find all the translations for property, method and method argument descriptions
    for property in get_element(value.documentElement, "properties").childNodes:
      property_name = get_text(get_element(property, "name", "anwv")).strip()
      property_description = re.sub(r"</?anwv/?>", "", get_text(get_element(property, "name", "anwv"))).strip()
      if property_description and property_description.find("[untr]") < 0:
        strings[locale][property_name + "Description"] = { "message": property_description }
    for method in get_element(value.documentElement, "methods").childNodes:
      method_name = get_text(get_element(method, "name", "anwv")).strip()
      method_description = re.sub(r"</?anwv/?>", "", get_element(method, "description", "anwv").firstChild.toxml()).strip()
      method_return_description = get_element(method, "return_description", "anwv").firstChild
      if method_description and method_description.find("[untr]") < 0:
        strings[locale][method_name + "Description"] = { "message": method_description }
      if method_return_description:
        method_return_description = re.sub(r"</?anwv/?>", "", method_return_description.toxml()).strip()
        if method_return_description.find("[untr]") < 0:
          strings[locale][method_name + "ReturnDescription"] = { "message": method_return_description }
      for argument in get_element(method, "arguments").childNodes:
        argument_name = get_text(get_element(argument, "name", "anwv")).strip()
        argument_description = re.sub(r"</?anwv/?>", "", get_element(argument, "description", "anwv").firstChild.toxml()).strip()
        if argument_description and argument_description.find("[untr]") < 0:
          strings[locale][method_name + "Argument" + argument_name + "Description"] = { "message": argument_description }

  # Translate the strings in the description
  process_body(descriptions, strings)

  strings["en"]["general_notes"] = { "message": "General notes"}
  strings["en"]["methods_and_properties"] = {"message": "Methods and properties"}

  pagedata = re.sub(r"</?anwv/?>", "", descriptions["en"].toxml())
  pagedata = "%s\n\n{%% set interface=%s %%}\n{%% include \"includes/interface\" %%}" % (pagedata, json.dumps(interface, indent=2, separators=(',', ': ')))

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

  for locale, value in data.iteritems():
    title = get_text(get_element(data[locale].documentElement, "title", "anwv")).strip()
    if title and title.find("[untr]") < 0:
      strings[locale]["title"] = {"message": title}

    descriptions[locale] = get_element(value.documentElement, "description", "anwv")


    # Table headers
    prefnamecol = get_text(get_element(value.documentElement, "prefnamecol", "anwv")).strip()
    if prefnamecol and prefnamecol.find("[untr]") < 0:
      strings[locale]["prefnamecol"] = { "message": prefnamecol }
    defaultcol = get_text(get_element(value.documentElement, "defaultcol", "anwv")).strip()
    if defaultcol and prefnamecol.find("[untr]") < 0:
      strings[locale]["defaultcol"] = { "message": defaultcol }
    descriptioncol = get_text(get_element(value.documentElement, "descriptioncol", "anwv")).strip()
    if descriptioncol and descriptioncol.find("[untr]") < 0:
      strings[locale]["descriptioncol"] = { "message": descriptioncol }
    # Table sections
    section_counter = 0
    for section in get_element(value.documentElement, "sections").childNodes:
      sectionid = get_text(get_element(section, "id", "anwv")).strip()
      if sectionid and sectionid.find("[untr]") < 0:
        strings[locale]["section" + str(section_counter) + "id"] = { "message": sectionid }
      sectiontitle = get_text(get_element(section, "title", "anwv")).strip()
      if sectiontitle and sectiontitle.find("[untr]") < 0:
        strings[locale]["section" + str(section_counter) + "title"] = { "message": sectiontitle }
      section_preference_counter = 0
      for section_preference in get_element(section, "preferences").childNodes:
        for section_preference_property in section_preference.childNodes:
          if section_preference_property.nodeType == Node.ELEMENT_NODE:
            value = re.sub(r"</?anwv/?>", "", section_preference_property.firstChild.toxml()).strip()
            value = re.sub(r'>\s*<attr\s+name="(\w+)">([^"<>]*)</attr\b', r' \1="\2"', value, flags=re.S)
            if value and value.find("[untr]") < 0:
              strings[locale]["section" + str(section_counter) + "preference" + str(section_preference_counter) + section_preference_property.tagName] = {
                "message": value
              }
        section_preference_counter += 1
      section_counter += 1

  process_body(descriptions, strings)

  pagedata = descriptions["en"].toxml()
  pagedata = "template=preftable\n\n%s" % pagedata

  # Save the page's HTML
  target = os.path.join(output_dir, "pages", pagename + ".raw")
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
  process_body(footers, strings, process_body(headers, strings))

  strings["en"]["maintainer_suffix"] = {"message": ""}
  strings["en"]["supplements_suffix"] = {"message": ""}

  # Load the main content from www/subscriptions.html (Generated by a sitescript)
  with open("subscriptions.html", "rb") as handle:
    subscriptions = handle.read()
    subscriptions = re.sub(r"%([\w]+)%([\<\s]+)", r"$\1$\2", subscriptions)
    subscriptions = re.sub(r"([\>\s]+)%([\w]+)%", r"\1$\2$", subscriptions)

  pagedata = "%s\n\n%s\n\n%s" % (headers["en"].toxml(), subscriptions.decode("utf-8"), footers["en"].toxml())

  # Save the page's HTML
  target = os.path.join(output_dir, "pages", pagename + ".raw")
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
