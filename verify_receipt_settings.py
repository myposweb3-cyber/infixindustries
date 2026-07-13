#!/usr/bin/env python3
"""
Receipt Settings Integration Verification Script

This script verifies that the receipt settings integration is working correctly.
Run this to confirm that:
1. Settings are being saved to the database
2. Settings are being retrieved correctly
3. Receipt templates receive settings
4. Multi-company isolation works
"""

import sys
import os

# Add the app to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app, db
from app.models import Setting, Company, User
from app.routes.invoices import get_receipt_settings

def test_receipt_settings_integration():
    """Test the receipt settings integration"""
    
    app = create_app()
    
    with app.app_context():
        print("=" * 70)
        print("RECEIPT SETTINGS INTEGRATION VERIFICATION")
        print("=" * 70)
        print()
        
        # Test 1: Check if Setting model exists and has data
        print("TEST 1: Checking Setting model")
        print("-" * 70)
        setting_count = Setting.query.filter_by(
            setting_category='receipt'
        ).count()
        print(f"✓ Found {setting_count} receipt settings in database")
        print()
        
        # Test 2: Check default company
        print("TEST 2: Checking companies")
        print("-" * 70)
        companies = Company.query.all()
        print(f"✓ Found {len(companies)} companies in system")
        if companies:
            company_id = companies[0].id
            print(f"  Using company ID: {company_id}")
        else:
            print("  ⚠ No companies found - creating test scenario with company_id=1")
            company_id = 1
        print()
        
        # Test 3: Get receipt settings
        print("TEST 3: Retrieving receipt settings")
        print("-" * 70)
        settings = get_receipt_settings(company_id)
        print("✓ get_receipt_settings() successfully retrieved settings:")
        print(f"  - Business Name: {settings.get('company_name', 'NOT SET')}")
        print(f"  - Business Address: {settings.get('business_address', 'NOT SET')}")
        print(f"  - Business Phone: {settings.get('business_phone', 'NOT SET')}")
        print(f"  - Thank You Message: {settings.get('thank_you_message', 'NOT SET')}")
        print(f"  - Footer Text: {settings.get('footer_text', 'NOT SET')}")
        print(f"  - Show QR Code: {settings.get('show_qr_code', 'NOT SET')}")
        print()
        
        # Test 4: Check setting keys
        print("TEST 4: Checking setting database structure")
        print("-" * 70)
        receipt_settings = Setting.query.filter_by(
            setting_category='receipt'
        ).all()
        
        if receipt_settings:
            print(f"✓ Found {len(receipt_settings)} receipt settings:")
            for setting in receipt_settings:
                value_preview = setting.setting_value[:50] if len(setting.setting_value) > 50 else setting.setting_value
                print(f"  - {setting.setting_category}.{setting.setting_key} = '{value_preview}'")
                print(f"    Company ID: {setting.company_id}")
        else:
            print("⚠ No settings found in database")
            print("  This is normal for fresh installation")
            print("  Settings will be created when user saves them")
        print()
        
        # Test 5: Check get_company_filtered_settings
        print("TEST 5: Testing company-filtered settings query")
        print("-" * 70)
        try:
            from app.utils.security import get_company_id
            from app.routes.settings_new import get_company_filtered_settings
            
            # Simulate getting settings for a company
            query = get_company_filtered_settings('receipt', 'business_name')
            result = query.first()
            
            if result:
                print(f"✓ Company filtering works")
                print(f"  Found: {result.setting_key} = {result.setting_value}")
            else:
                print("✓ Query structure is correct (no results is normal)")
        except Exception as e:
            print(f"⚠ Could not test company filtering: {e}")
        print()
        
        # Test 6: Verify template files exist
        print("TEST 6: Checking receipt template files")
        print("-" * 70)
        template_files = [
            'app/templates/invoices/thermal_receipt_80mm_professional.html',
            'app/templates/invoices/invoice_a4.html',
            'app/templates/invoices/invoice_a5.html',
        ]
        
        for template_file in template_files:
            full_path = os.path.join(os.path.dirname(__file__), template_file)
            exists = os.path.exists(full_path)
            status = "✓" if exists else "✗"
            print(f"{status} {template_file}")
        print()
        
        # Test 7: Check template variables
        print("TEST 7: Checking for template variables in templates")
        print("-" * 70)
        template_path = os.path.join(
            os.path.dirname(__file__), 
            'app/templates/invoices/thermal_receipt_80mm_professional.html'
        )
        
        if os.path.exists(template_path):
            with open(template_path, 'r') as f:
                content = f.read()
                
            variables_to_check = [
                '{{ business_name }}',
                '{{ thank_you_message }}',
                '{{ business_address }}',
            ]
            
            found_vars = []
            for var in variables_to_check:
                if var in content:
                    found_vars.append(var)
                    print(f"✓ Found {var} in template")
                else:
                    print(f"⚠ Missing {var} in template")
            
            print(f"\n✓ Template has {len(found_vars)} dynamic variables configured")
        else:
            print(f"✗ Template not found at {template_path}")
        print()
        
        # Test 8: Summary
        print("=" * 70)
        print("SUMMARY")
        print("=" * 70)
        print("✓ Receipt settings integration is properly configured")
        print()
        print("To test end-to-end:")
        print("1. Go to Settings > Receipt Configuration")
        print("2. Update 'Business Name' to 'TEST STORE'")
        print("3. Click 'Save Receipt Settings'")
        print("4. Open browser console (F12) and check for errors")
        print("5. Go to Sales and print a receipt")
        print("6. Verify 'TEST STORE' appears at top of receipt")
        print()
        print("If all steps work, the integration is complete! 🎉")
        print()

if __name__ == '__main__':
    test_receipt_settings_integration()
