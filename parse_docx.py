import sys, zipfile, xml.etree.ElementTree as ET

def extract_docx_text(path):
    with zipfile.ZipFile(path) as z:
        xml_content = z.read('word/document.xml')
        tree = ET.fromstring(xml_content)
        texts = [node.text for node in tree.iter() if node.text]
        return ' '.join(texts)

if __name__ == '__main__':
    for path in sys.argv[1:]:
        print(f"=== {path} ===")
        print(extract_docx_text(path))
