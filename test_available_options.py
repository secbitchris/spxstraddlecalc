#!/usr/bin/env python3
"""
Test script to find available SPX options contracts
"""

import os
import pytz
from datetime import date, datetime
from polygon import RESTClient

def test_available_options():
    """Test what options contracts are available"""
    
    api_key = os.getenv('POLYGON_API_KEY')
    if not api_key:
        print("❌ POLYGON_API_KEY not found")
        return
    
    client = RESTClient(api_key)
    et_tz = pytz.timezone('US/Eastern')
    
    # Test with December 16, 2024
    test_date = date(2024, 12, 16)
    print(f"🗓️ Testing for date: {test_date}")
    
    # Try to find SPX options contracts
    print(f"\n🔍 Searching for SPX options contracts...")
    
    try:
        # Search for options contracts with SPX in the name
        contracts = client.list_options_contracts(
            underlying_ticker="SPX",
            expiration_date=test_date,
            limit=10
        )
        
        contract_list = list(contracts)
        print(f"✅ Found {len(contract_list)} SPX options contracts for {test_date}")
        
        if contract_list:
            for i, contract in enumerate(contract_list[:5]):  # Show first 5
                print(f"   {i+1}. {contract.ticker}")
                print(f"      Strike: ${contract.strike_price}")
                print(f"      Type: {contract.contract_type}")
                print(f"      Expiry: {contract.expiration_date}")
                print()
        else:
            print("   No SPX contracts found for this date")
            
            # Try searching for any SPX contracts
            print(f"\n🔍 Searching for any SPX options contracts...")
            all_contracts = client.list_options_contracts(
                underlying_ticker="SPX",
                limit=10
            )
            
            all_contract_list = list(all_contracts)
            print(f"✅ Found {len(all_contract_list)} total SPX options contracts")
            
            if all_contract_list:
                for i, contract in enumerate(all_contract_list[:5]):
                    print(f"   {i+1}. {contract.ticker}")
                    print(f"      Strike: ${contract.strike_price}")
                    print(f"      Type: {contract.contract_type}")
                    print(f"      Expiry: {contract.expiration_date}")
                    print()
    
    except Exception as e:
        print(f"❌ Error searching SPX contracts: {e}")
        
        # Try searching for SPXW (SPX Weeklys) instead
        print(f"\n🔍 Trying SPXW (SPX Weeklys)...")
        try:
            spxw_contracts = client.list_options_contracts(
                underlying_ticker="SPXW",
                expiration_date=test_date,
                limit=10
            )
            
            spxw_list = list(spxw_contracts)
            print(f"✅ Found {len(spxw_list)} SPXW options contracts for {test_date}")
            
            if spxw_list:
                for i, contract in enumerate(spxw_list[:5]):
                    print(f"   {i+1}. {contract.ticker}")
                    print(f"      Strike: ${contract.strike_price}")
                    print(f"      Type: {contract.contract_type}")
                    print(f"      Expiry: {contract.expiration_date}")
                    print()
        
        except Exception as e2:
            print(f"❌ Error searching SPXW contracts: {e2}")

if __name__ == "__main__":
    test_available_options() 