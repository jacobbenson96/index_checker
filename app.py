from flask import Flask, request, render_template, send_file, session
import zipfile
from lxml import etree as ET
import csv
import io
from html import unescape
import re

app = Flask(__name__)
app.secret_key = 'household-key'  # Required for using session

# Utility function to strip HTML from description
def strip_html(text):
    clean = re.compile('<.*?>')
    return re.sub(clean, '', unescape(text)).strip()

# Function to extract data from KMZ (in memory)
def extract_placemark_data(file_obj):
    file_obj.seek(0)
    with zipfile.ZipFile(file_obj, 'r') as kmz:
        kml_filename = [name for name in kmz.namelist() if name.endswith('.kml')]
        if not kml_filename:
            return []
        with kmz.open(kml_filename[0]) as kml_file:
            kml_content = kml_file.read()

    parser = ET.XMLParser(recover=True)
    root = ET.fromstring(kml_content, parser)
    ns = root.nsmap

    placemarks = root.findall(".//kml:Placemark", namespaces=ns)
    placemark_data = []

    for placemark in placemarks:
        name = placemark.find("kml:name", namespaces=ns)
        address = placemark.find("kml:address", namespaces=ns)
        description = placemark.find("kml:description", namespaces=ns)

        description_text = ""
        if description is not None and description.text:
            description_text = strip_html(description.text)

        coords = placemark.find(".//kml:coordinates", namespaces=ns)
        longitude, latitude = "", ""
        if coords is not None and coords.text:
            try:
                coord_text = coords.text.strip()
                coord_parts = coord_text.split(',')
                if len(coord_parts) >= 2:
                    longitude = coord_parts[0].strip()
                    latitude = coord_parts[1].strip()
            except:
                pass

        extended_data = {}
        ext = placemark.find(".//kml:ExtendedData", namespaces=ns)
        if ext is not None:
            for data in ext.findall(".//kml:Data", namespaces=ns):
                key = data.get("name")
                value = data.find("kml:value", namespaces=ns)
                extended_data[key] = value.text.strip() if value is not None else ""

        placemark_data.append({
            "Name": name.text.strip() if name is not None else "",
            "Address": address.text.strip() if address is not None else "",
            "Description": description_text,
            "Latitude": latitude,
            "Longitude": longitude,
            **extended_data
        })

    return placemark_data

# Homepage with file upload and results
@app.route('/', methods=['GET', 'POST'])
def home():
    if request.method == 'POST':
        file = request.files.get('kmz_file')
        if file and file.filename.endswith('.kmz'):

            # Store filename and process file
            session['last_uploaded'] = file.filename
            data = extract_placemark_data(file)

            # Build CSV in memory
            output = io.StringIO()
            writer = csv.DictWriter(output, fieldnames=data[0].keys())
            writer.writeheader()
            writer.writerows(data)
            csv_data = output.getvalue()
            output.close()

            # Store CSV content in session for download
            session['csv_data'] = csv_data

            return render_template('results.html', data=data, csv=csv_data)

        return 'Please upload a valid .kmz file.'
    
    return render_template('index.html')

# Download the CSV file
@app.route('/download')
def download_csv():
    csv_data = session.get('csv_data')
    if not csv_data:
        return "No CSV data available. Please upload a file first."

    original_name = session.get('last_uploaded', 'household.kmz')
    csv_name = original_name.rsplit('.', 1)[0] + '_household.csv'

    return send_file(
        io.BytesIO(csv_data.encode()),
        mimetype='text/csv',
        as_attachment=True,
        download_name=csv_name
    )

if __name__ == '__main__':
    app.run(debug=True)
