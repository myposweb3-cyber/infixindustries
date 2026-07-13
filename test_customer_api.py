#!/usr/bin/env python
"""Test script to diagnose customer API issues"""
import requests
import json

# Test data for a new customer
customer_data = {
    'name': 'Test Customer',
    'phone': '0300-1234567',
    'email': 'test@example.com',
    'address': 'Test Address',
    'notes': 'Test notes',
    'preferred_payment_method': 'Cash',
    'credit_limit': 50000,
    'current_balance': 0
}

# Try to create a customer
url = 'http://localhost:5000/customers/api/customers'

print("Testing Customer API endpoint...")
print(f"URL: {url}")
print(f"Data: {json.dumps(customer_data, indent=2)}")
print("\n" + "="*50 + "\n")

try:
    # First, try GET to see if we can reach the endpoint
    print("1. Testing GET /customers/api/customers...")
    response = requests.get('http://localhost:5000/customers/api/customers')
    print(f"Status: {response.status_code}")
    print(f"Response: {response.text[:200]}")
    
    print("\n" + "="*50 + "\n")
    
    # Now try POST
    print("2. Testing POST /customers/api/customers...")
    headers = {
        'Content-Type': 'application/json',
        'Accept': 'application/json'
    }
    response = requests.post(url, json=customer_data, headers=headers)
    print(f"Status: {response.status_code}")
    print(f"Response:\n{response.text}")
    
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
