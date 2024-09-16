import re
import requests
import json
import inspect
import os
import shutil
import base64
from slither.slither import Slither
from slither.detectors.abstract_detector import AbstractDetector
from slither.detectors import all_detectors
from solc_select import solc_select
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)

CORS(app, resources={r"/*": {"origins": "*"}})

def get_contract_code(blockchain, contract_address, code=None):
    """
    Retrieves the contract code from a given blockchain and contract address.
    If `code` is provided, it creates a contract file with the given code.
    If `code` is not provided, it retrieves the contract code from the blockchain API.

    Args:
        blockchain (str): The name of the blockchain.
        contract_address (str): The address of the contract.
        code (str, optional): The contract code. Defaults to None.

    Returns:
        str: The name of the contract file or the main contract file.

    Raises:
        None

    """
    if not code:
        # Retrieve contract code from the blockchain API

        api_url, api_key = os.environ[blockchain.upper()].split(",")

        url = f"https://{api_url}/api?module=contract&action=getsourcecode&address={contract_address}&apikey={api_key}"

        response = requests.get(url)

        if response.status_code == 200:
            contract_code = response.json()["result"][0]["SourceCode"]
            compiler_version = response.json()["result"][0]["CompilerVersion"]
            contract_name = response.json()["result"][0]["ContractName"]

            # get solidity version and adjust solidity compiler version
            solidity_version = get_solidity_version(compiler_version)
            solc_select.switch_global_version(solidity_version, True)

            # create the contract directory if it doesn't exist
            if not os.path.exists(f"contracts/{blockchain}/{contract_address}"):
                os.makedirs(f"contracts/{blockchain}/{contract_address}")

            # change active directory to the contract directory
            os.chdir(f"contracts/{blockchain}/{contract_address}")

            # single file contract
            if contract_code[0] != "{":
                contract_lines = ["\n", "\n", "\n", "\n"] + contract_code.split("\n")

                with open(f"{contract_name}.sol", "w") as f:
                    f.writelines(contract_lines)

                return f"{contract_name}.sol"

            # multi file contract
            else:
                contract_files = json.loads(contract_code[1:-1])['sources']
                main_contract = ""
                for file_name, file_content in contract_files.items():
                    contract_lines = file_content['content']

                    # find contract name in the file
                    if "contract " + contract_name in contract_lines:
                        main_contract = file_name

                for file_name, file_content in contract_files.items():
                    contract_lines = file_content['content']

                    if main_contract == file_name:

                        if not os.path.exists(os.path.dirname(file_name)):
                            os.makedirs(os.path.dirname(file_name))

                        with open(file_name, "w") as f:
                            f.writelines(contract_lines)

                    else:
                        if not os.path.exists(os.path.dirname(file_name)):
                            os.makedirs(os.path.dirname(file_name))

                        with open(file_name, "w") as f:
                            f.writelines(contract_lines)

                return main_contract

        else:
            print("Error: Unable to retrieve contract code")

    else:
        # Create contract file with the provided code

        # create the contract directory if it doesn't exist
        if not os.path.exists("contracts/no-bc/contract"):
            os.makedirs("contracts/no-bc/contract")

        # change active directory to the contract directory
        os.chdir("contracts/no-bc/contract")

        with open("contract.sol", "w") as f:
            f.writelines(code)

        solidity_version = ""
        
        with open("contract.sol", "r") as f:
            for line in f:
                # read solidity version from the code
                if "pragma solidity" in line:
                    solidity_version = re.search(r'\d+\.\d+\.\d+', line).group(0)
                    break
            
        # set the solidity version
        solc_select.switch_global_version(solidity_version, True)

        return "contract.sol"

def analyze_contract_code(contract):
    """
    Analyzes the given contract code using Slither detectors and returns a list of filtered results.

    Args:
        contract: The contract code to be analyzed.

    Returns:
        A list of filtered results, where each result is a dictionary containing the following keys:
        - "check": The name of the check that detected the issue.
        - "description": A description of the issue.
        - "impact": The impact of the issue.
        - "confidence": The confidence level of the issue.

    """
    slither_obj = Slither(contract)

    detectors_ = [getattr(all_detectors, name) for name in dir(all_detectors)]
    detectors = [d for d in detectors_ if inspect.isclass(d) and issubclass(d, AbstractDetector)]

    for detector in detectors:
        slither_obj.register_detector(detector)

    results = slither_obj.run_detectors()

    filtered_results = []
    for result in results:
        if result != []:
            for issue in result:
                filtered_result = {
                    "check": issue["check"],
                    "description": issue["description"],
                    "impact": issue["impact"],
                    "confidence": issue["confidence"],
                }
                filtered_results.append(filtered_result)

    return filtered_results

import re

def get_solidity_version(compiler_version):
    """
    Extracts the solidity version from the given compiler version.

    Args:
        compiler_version (str): The compiler version string.

    Returns:
        str: The extracted solidity version string, or an empty string if no version is found.
    """
    version = re.search(r'v(\d+\.\d+\.\d+)', compiler_version)
    if version:
        return version.group(1)
    else:
        return ""



def delete_contract_directory():
    """
    Deletes all files and directories within the current directory, except for the root directory.

    This function iterates through all files and directories within the current directory and deletes them.
    If a file is encountered, it is unlinked (deleted). If a directory is encountered, it is recursively
    removed using the `shutil.rmtree` function.

    Note: This function does not delete the root directory itself.

    Raises:
        OSError: If there is an error while deleting a file or directory.

    """
    os.chdir("..")
    for filename in os.listdir("."):
        file_path = os.path.join(".", filename)
        try:
            if os.path.isfile(file_path) or os.path.islink(file_path):
                os.unlink(file_path)
            elif os.path.isdir(file_path):
                shutil.rmtree(file_path)
        except Exception as e:
            print('Failed to delete %s. Reason: %s' % (file_path, e))

    # Reset active directory to the root directory
    os.chdir("../..")

@app.route('/', methods=['GET'])
def home():
    """
    This function handles the home route of the IARD Solutions API.

    Returns:
        str: A welcome message.
    """
    return 'Welcome to the IARD Solutions API'

@app.route('/analyze', methods=['GET'])
def analyze_contract():    
    """
    Analyzes a smart contract based on the provided blockchain, contract address, and code.

    Returns the analysis result in JSON format.

    Parameters:
    - blockchain (str): The blockchain on which the contract is deployed.
    - contract_address (str): The address of the contract to be analyzed.
    - code (str): The code of the contract to be analyzed, encoded in base64.

    Returns:
    - JSON: The analysis result, including any errors or the analysis output.

    Raises:
    - MissingBlockchainOrContractAddressError: If either the blockchain or contract address is missing.
    - UnableToRetrieveContractCodeError: If the contract code cannot be retrieved.

    """
    blockchain = request.args.get('blockchain')
    contract_address = request.args.get('contract')
    code = request.args.get('code')
  
    if not blockchain or not contract_address:
        if code:
            print(code)
            decoded_code = base64.b64decode(code).decode('utf-8')
            print(decoded_code)
            contract = get_contract_code(blockchain, contract_address, decoded_code)
            if not contract:
                return jsonify({'error': 'Unable to retrieve contract code'}), 400
            slither_result = analyze_contract_code(contract)
            delete_contract_directory()
            return jsonify({'result': slither_result})
        else:
            return jsonify({'error': 'Missing blockchain or contract address'}), 400
  
    contract = get_contract_code(blockchain, contract_address)
    if not contract:
        return jsonify({'error': 'Unable to retrieve contract code'}), 400
    slither_result = analyze_contract_code(contract)
    delete_contract_directory()
    return jsonify({'result': slither_result})

if __name__ == '__main__':
  app.run(host='0.0.0.0', port=80)