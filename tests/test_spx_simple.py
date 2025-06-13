#!/usr/bin/env python3
"""
Simple test for SPX options
"""

import os
from datetime import date
from polygon import RESTClient

def test_spx_simple():
    api_key = os.getenv('POLYGON_API_KEY')
    if not api_key:
        print("❌ No API key")
        return
    
    client = RESTClient(api_key)
    today = date(2025, 6, 13)
    
    print(f"🗓️ Testing for: {today}")
    
    # Test SPX
    try:
        spx_contracts = list(client.list_options_contracts(
            underlying_ticker="SPX",
            expiration_date=today,
            limit=5
        ))
        print(f"📊 SPX contracts: {len(spx_contracts)}")
        if spx_contracts:
            print(f"   First: {spx_contracts[0].ticker}")
    except Exception as e:
        print(f"❌ SPX error: {e}")
    
    # Test SPXW
    try:
        spxw_contracts = list(client.list_options_contracts(
            underlying_ticker="SPXW",
            expiration_date=today,
            limit=5
        ))
        print(f"📊 SPXW contracts: {len(spxw_contracts)}")
        if spxw_contracts:
            print(f"   First: {spxw_contracts[0].ticker}")
    except Exception as e:
        print(f"❌ SPXW error: {e}")

if __name__ == "__main__":
    test_spx_simple() 