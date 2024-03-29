import requests

from typing import List, Dict, Any
from dateutil import parser
from datetime import datetime, timezone

import xml.etree.ElementTree as ET
import xmltodict
import logging
import math

from flask import Flask, jsonify, request
from typing import Union
from geopy.geocoders import Nominatim
import requests
import xml.dom.minidom

app = Flask(__name__)

# Configure logging
logging.basicConfig(filename='iss_tracker.log', level=logging.ERROR)

# Define the mean Earth radius constant
MEAN_EARTH_RADIUS = 6371.0  # in kilometers

def parse_comment_from_xml(xml_url):
    """Parse comments from XML data.

    Args:
        xml_url (str): URL of the XML data.

    Returns:
        Dict[str, Union[str, List[str]]]: Parsed comments or error message.
    """
    try:
        # Fetch XML content from the URL
        response = requests.get(xml_url)
        response.raise_for_status()  # Raise an error for bad responses
        xml_content = response.content.decode()

        # Parse the XML content
        dom = xml.dom.minidom.parseString(xml_content)

        # Get all COMMENT elements
        comments = dom.getElementsByTagName('COMMENT')

        # Extract text from COMMENT elements
        comment_texts = [comment.firstChild.nodeValue.strip() for comment in comments if comment.firstChild]

        # Return the extracted comment texts
        return {'comments': comment_texts}
    except Exception as e:
        # Handle any exceptions
        return {'error': str(e)}
    
def parse_header_from_xml(xml_url):
    """Parse header from XML data.

    Args:
        xml_url (str): URL of the XML data.

    Returns:
        Dict[str, Union[str, List[str]]]: Parsed header or error message.
    """
    try:
        # Fetch XML content from the URL
        response = requests.get(xml_url)
        response.raise_for_status()  # Raise an error for bad responses
        xml_content = response.content

        # Parse the XML content using ElementTree
        root = ET.fromstring(xml_content)

        # Find the header element
        header_element = root.find('.//header')

        if header_element is None:
            raise ValueError("Header element not found in the XML")

        # Extract header data
        header_data = {}
        for child in header_element:
            header_data[child.tag] = child.text.strip()

        return {'header': header_data}
    except Exception as e:
        # Handle any exceptions
        return {'error': str(e)}
    
def parse_metadata_from_xml(xml_url):
    """Parse metadata from XML data.

    Args:
        xml_url (str): URL of the XML data.

    Returns:
        Dict[str, Union[str, List[str]]]: Parsed metadata or error message.
    """
    try:
        # Fetch XML content from the URL
        response = requests.get(xml_url)
        response.raise_for_status()  # Raise an error for bad responses
        xml_content = response.content.decode()

        # Parse the XML content
        dom = xml.dom.minidom.parseString(xml_content)

        # Get all metadata elements
        metadata_elements = dom.getElementsByTagName('metadata')

        # Extract text from metadata elements
        metadata_texts = []

        # Iterate through each metadata element
        for metadata_element in metadata_elements:
            metadata = {}
            # Iterate through child elements of metadata
            for child in metadata_element.childNodes:
                # Check if the child is an element node
                if child.nodeType == child.ELEMENT_NODE:
                    # Add key-value pair to metadata dictionary
                    metadata[child.tagName] = child.firstChild.nodeValue.strip()
            # Append metadata dictionary to the list
            metadata_texts.append(metadata)

        # Return the extracted metadata
        return {'metadata': metadata_texts}
    except Exception as e:
        # Handle any exceptions
        return {'error': str(e)}

def parse_iss_data(xml_data: dict) -> List[Dict[str, Any]]:
    """Parse the ISS data and store it in a list of dictionaries format.

    Args:
        xml_data (dict): Parsed XML data in dictionary format.

    Returns:
        List[Dict[str, Union[str, float]]]: List of dictionaries containing ISS data.
    """
    iss_data = []

    try:
        # Extract necessary information based on your XML structure
        state_vectors = xml_data.get("ndm", {}).get("oem", {}).get("body", {}).get("segment", {}).get("data", {}).get("stateVector", [])

        if not state_vectors:
            raise ValueError("No state vectors found in the XML data.")

        for state_vector in state_vectors:
            data_point = {
                "EPOCH": state_vector.get("EPOCH", ""),
                "X": float(state_vector.get("X", {}).get("#text", 0)),
                "Y": float(state_vector.get("Y", {}).get("#text", 0)),
                "Z": float(state_vector.get("Z", {}).get("#text", 0)),
                "X_DOT": float(state_vector.get("X_DOT", {}).get("#text", 0)),
                "Y_DOT": float(state_vector.get("Y_DOT", {}).get("#text", 0)),
                "Z_DOT": float(state_vector.get("Z_DOT", {}).get("#text", 0)),
            }
            iss_data.append(data_point)

        return iss_data
    except Exception as e:
        logging.error(f"Error parsing ISS data: {e}")
        return []

def calculate_average_speed(iss_data: List[Dict[str, str]]) -> float:
    """Calculate the average speed over the whole ISS data set.

    Args:
        iss_data (List[Dict[str, Union[str, float]]]): List of dictionaries containing ISS data.

    Returns:
        float: Average speed over the whole data set.
    """
    try:
        total_speed = sum(((data_point["X_DOT"])**2 + (data_point["Y_DOT"])**2 + (data_point["Z_DOT"])**2)**0.5
                          for data_point in iss_data)
        return total_speed / len(iss_data)
    except ZeroDivisionError:
        return 0.0

def calculate_instantaneous_speed(data_point: Dict[str, Union[str, float]]) -> float:
    """Calculate instantaneous speed for a specific data point."""
    speed = (
        float(data_point["X_DOT"])**2 +
        float(data_point["Y_DOT"])**2 +
        float(data_point["Z_DOT"])**2
    )**0.5
    return speed

def find_closest_data_point(iss_data: List[Dict[str, str]]) -> Dict[str, str]:
    """Find the closest data point to the current time.

    Args:
        iss_data (List[Dict[str, Union[str, float]]]): List of dictionaries containing ISS data.

    Returns:
        Dict[str, Union[str, float]]: Dictionary containing the closest data point.
    """
    now = datetime.utcnow().replace(tzinfo=timezone.utc)

    # Create a copy of the original list before sorting
    sorted_data = sorted(iss_data, key=lambda x: abs(now - parser.isoparse(x["EPOCH"])))

    return sorted_data[0]

def print_data_range(iss_data: List[Dict[str, str]]):
    """Print the range of data using timestamps from the first and last epochs.

    Args:
        iss_data (List[Dict[str, Union[str, float]]]): List of dictionaries containing ISS data.
    """
    if iss_data:
        start_epoch = iss_data[0]["EPOCH"]
        end_epoch = iss_data[-1]["EPOCH"]
        print(f"Data range from {start_epoch} to {end_epoch}")
        
def calculate_location_for_epoch(epoch_data: Dict[str, Union[str, float]]) -> Dict[str, Union[str, float]]:
    """Calculate latitude, longitude, altitude, and geoposition for a given epoch data.

    Args:
        epoch_data (Dict[str, Union[str, float]]): Dictionary containing ISS data for a specific epoch.

    Returns:
        Dict[str, Union[str, float]]: Dictionary containing latitude, longitude, altitude, and geoposition.
    """
    x = epoch_data.get("X", 0)
    y = epoch_data.get("Y", 0)
    z = epoch_data.get("Z", 0)

    # Calculate latitude
    lat = math.degrees(math.atan2(z, math.sqrt(x**2 + y**2)))

    # Calculate altitude
    alt = math.sqrt(x**2 + y**2 + z**2) - MEAN_EARTH_RADIUS

    # Calculate longitude
    lon = math.degrees(math.atan2(y, x)) - ((datetime.utcnow().hour - 12) + (datetime.utcnow().minute / 60)) * (360 / 24) + 19

    # Check and adjust longitude if it falls outside the range [-180, 180]
    if lon > 180:
        lon = -180 + (lon - 180)
    elif lon < -180:
        lon = 180 + (lon + 180)

    # Initialize geocoder
    geolocator = Nominatim(user_agent="iss_tracker")

    # Determine geoposition from latitude and longitude
    location = geolocator.reverse(f"{lat}, {lon}")

    return {
        "latitude": lat,
        "longitude": lon,
        "altitude": alt,
        "geoposition": location.address if location else "Unknown"
    }

# Route to return the comment object parsed from the XML file
@app.route('/comment', methods=['GET'])
def get_comment():
    """
    Fetches and returns the 'comment' dictionary object from the ISS data.

    Returns:
        dict: Dictionary containing the 'comment' data.
    """
    xml_url = 'https://nasa-public-data.s3.amazonaws.com/iss-coords/current/ISS_OEM/ISS.OEM_J2K_EPH.xml'
    comment_data = parse_comment_from_xml(xml_url)
    
    if isinstance(comment_data, dict) and 'error' in comment_data:
        # Handle error response
        return jsonify(comment_data), 500

    return jsonify(comment_data)

# Route to return the 'header' dictionary object from the ISS data
@app.route('/header', methods=['GET'])
def get_header():
    """
    Fetches and returns the 'header' dictionary object from the ISS data.

    Returns:
        dict: Dictionary containing the 'header' data.
    """
    header = parse_header_from_xml('https://nasa-public-data.s3.amazonaws.com/iss-coords/current/ISS_OEM/ISS.OEM_J2K_EPH.xml')
    
    # Check if metadata was fetched successfully
    if 'header' in header:
        # Return metadata as a JSON response
        return header
    else:
        # Return an error response
        return {'error': 'Failed to fetch header'}, 500

# Route to return the 'metadata' dictionary object from the ISS data
@app.route('/metadata')
def get_metadata():
    """
    Fetches and returns the 'metadata' dictionary object from the ISS data.

    Returns:
        dict: Dictionary containing the 'metadata' data.
    """
    metadata = parse_metadata_from_xml('https://nasa-public-data.s3.amazonaws.com/iss-coords/current/ISS_OEM/ISS.OEM_J2K_EPH.xml')
    
    # Check if metadata was fetched successfully
    if 'metadata' in metadata:
        # Return metadata as a JSON response
        return metadata
    else:
        # Return an error response
        return {'error': 'Failed to fetch metadata'}, 500

# Route to return the entire data set
@app.route('/epochs', methods=['GET'])
def get_epochs():
    """
    Fetches and returns the entire data set of ISS state vectors.

    Returns:
        dict: Dictionary containing the entire data set.
    """
    try:
        # Make a GET request to the ISS data URL
        response = requests.get(url='https://nasa-public-data.s3.amazonaws.com/iss-coords/current/ISS_OEM/ISS.OEM_J2K_EPH.xml')

        # Check if the request was successful (status code 200)
        if response.status_code == 200:
            # Parse the XML content using xmltodict and convert to dictionary
            data_dict = xmltodict.parse(response.content)

            # Extract state vector information from the parsed data
            iss_data = parse_iss_data(data_dict)

            # Return the entire data set as JSON
            return jsonify(iss_data)

        else:
            # Return an error message if the request fails
            return jsonify({"error": f"Failed to fetch ISS data. Status code: {response.status_code}"}), 500

    except Exception as e:
        # Log any errors
        logging.error(f"Error: {e}")
        return jsonify({"error": "Internal server error"}), 500
    
def get_entire_data_set():
    """
    Helper function to fetch and return the entire data set of ISS state vectors.

    Returns:
        dict: Dictionary containing the entire data set.
    """
    try:
        response = requests.get(url='https://nasa-public-data.s3.amazonaws.com/iss-coords/current/ISS_OEM/ISS.OEM_J2K_EPH.xml')
        if response.status_code == 200:
            data_dict = xmltodict.parse(response.content)
            iss_data = parse_iss_data(data_dict)
            return jsonify(iss_data)
        else:
            return jsonify({"error": f"Failed to fetch ISS data. Status code: {response.status_code}"}), 500

    except Exception as e:
        logging.error(f"Error: {e}")
        return jsonify({"error": f"An error occurred: {e}"}), 500

@app.route('/epochs?limit=int&offset=int', methods=['GET'])
def get_modified_epochs_list():
    """
    Fetches and returns a modified subset of the ISS state vector data based on query parameters.

    Returns:
        dict: Dictionary containing the modified data set based on limit and offset parameters.
    """
    try:
        # Get limit and offset from query parameters
        limit = int(request.args.get('limit', default=10))  # default limit is 10   
        offset = int(request.args.get('offset', default=0))  # default offset is 0  

        response = requests.get(url=f'https://nasa-public-data.s3.amazonaws.com/iss-coords/current/ISS_OEM/ISS.OEM_J2K_EPH.xml?limit={limit}&offset={offset}')
        if response.status_code == 200:
            data_dict = xmltodict.parse(response.content)
            iss_data = parse_iss_data(data_dict)

            return jsonify(iss_data)
        else:
            return jsonify({"error": f"Failed to fetch ISS data. Status code: {response.status_code}"}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# Route to get state vectors for a specific Epoch from the data set
@app.route('/epochs/<epoch>', methods=['GET'])
def get_state_vectors_for_epoch(epoch: str):
    """
    Fetches and returns the state vectors for a specific epoch from the ISS data set.

    Args:
        epoch (str): The epoch for which state vectors are requested.

    Returns:
        dict: Dictionary containing the state vectors for the specified epoch.
    """
    try:
        response = requests.get(url='https://nasa-public-data.s3.amazonaws.com/iss-coords/current/ISS_OEM/ISS.OEM_J2K_EPH.xml')
        if response.status_code == 200:
            data_dict = xmltodict.parse(response.content)
            iss_data = parse_iss_data(data_dict)

            # Find data for the specified epoch
            epoch_data = [data_point for data_point in iss_data if data_point["EPOCH"] == epoch]
            
            if epoch_data:
                return jsonify(epoch_data)
            else:
                return jsonify({"error": f"No data found for the specified epoch: {epoch}"}), 404
        else:
            return jsonify({"error": f"Failed to fetch ISS data. Status code: {response.status_code}"}), 500

    except Exception as e:
        logging.error(f"Error: {e}")
        return jsonify({"error": f"An error occurred: {e}"}), 500

# Route to get instantaneous speed for a specific Epoch in the data set
@app.route('/epochs/<epoch>/speed', methods=['GET'])
def get_instantaneous_speed_for_epoch(epoch: str):
    """
    Fetches and returns the instantaneous speed for a specific epoch from the ISS data set.

    Args:
        epoch (str): The epoch for which instantaneous speed is requested.

    Returns:
        dict: Dictionary containing the instantaneous speed for the specified epoch.
    """
    try:
        response = requests.get(url='https://nasa-public-data.s3.amazonaws.com/iss-coords/current/ISS_OEM/ISS.OEM_J2K_EPH.xml')
        if response.status_code == 200:
            data_dict = xmltodict.parse(response.content)
            iss_data = parse_iss_data(data_dict)

            # Find data for the specified epoch
            epoch_data = [data_point for data_point in iss_data if data_point["EPOCH"] == epoch]

            if epoch_data:
                # Calculate instantaneous speed for the specified epoch
                speed = calculate_instantaneous_speed(epoch_data[0])
                return jsonify({"instantaneous_speed": speed})
            else:
                return jsonify({"error": f"No data found for the specified epoch: {epoch}"}), 404
        else:
            return jsonify({"error": f"Failed to fetch ISS data. Status code: {response.status_code}"}), 500

    except Exception as e:
        logging.error(f"Error: {e}")
        return jsonify({"error": f"An error occurred: {e}"}), 500

# Route to get latitude, longitude, altitude, and geoposition for a specific epoch in the data set
@app.route('/epochs/<epoch>/location', methods=['GET'])
def get_location_for_epoch(epoch: str):
    """
    Fetches and returns the location data for a specific epoch from the ISS data set.

    Args:
        epoch (str): The epoch for which location data is requested.

    Returns:
        dict: Dictionary containing the location data for the specified epoch.
    """
    try:
        response = requests.get(url='https://nasa-public-data.s3.amazonaws.com/iss-coords/current/ISS_OEM/ISS.OEM_J2K_EPH.xml')
        if response.status_code == 200:
            data_dict = xmltodict.parse(response.content)
            iss_data = parse_iss_data(data_dict)

            # Find data for the specified epoch
            epoch_data = next((data_point for data_point in iss_data if data_point["EPOCH"] == epoch), None)
            
            if epoch_data:
                # Calculate location for the epoch
                location_data = calculate_location_for_epoch(epoch_data)
                return jsonify(location_data)
            else:
                return jsonify({"error": f"No data found for the specified epoch: {epoch}"}), 404
        else:
            return jsonify({"error": f"Failed to fetch ISS data. Status code: {response.status_code}"}), 500

    except Exception as e:
        logging.error(f"Error: {e}")
        return jsonify({"error": f"An error occurred: {e}"}), 500

# Route to get latitude, longitude, altitude, geoposition, and speed for the epoch that is nearest in time
@app.route('/now', methods=['GET'])
def get_data_for_nearest_epoch():
    """
    Fetches and returns data for the epoch nearest to the current time from the ISS data set.

    Returns:
        dict: Dictionary containing data for the epoch nearest to the current time.
    """
    try:
        response = requests.get(url='https://nasa-public-data.s3.amazonaws.com/iss-coords/current/ISS_OEM/ISS.OEM_J2K_EPH.xml')
        if response.status_code == 200:
            data_dict = xmltodict.parse(response.content)
            iss_data = parse_iss_data(data_dict)

            # Find the closest data point to 'now'
            closest_data_point = find_closest_data_point(iss_data)

            # Calculate instantaneous speed closest to 'now'
            instantaneous_speed = calculate_instantaneous_speed(closest_data_point)

            # Calculate latitude, longitude, altitude, and geoposition for the closest epoch
            location_data = calculate_location_for_epoch(closest_data_point)

            # Create a JSON object containing the required information
            result = {
                "latitude": location_data["latitude"],
                "longitude": location_data["longitude"],
                "altitude": location_data["altitude"],
                "geoposition": location_data["geoposition"],
                "speed": instantaneous_speed
            }

            return jsonify(result)
        else:
            return jsonify({"error": f"Failed to fetch ISS data. Status code: {response.status_code}"}), 500

    except Exception as e:
        logging.error(f"Error: {e}")
        return jsonify({"error": f"An error occurred: {e}"}), 500
    
if __name__ == '__main__':
    app.run(debug=True)