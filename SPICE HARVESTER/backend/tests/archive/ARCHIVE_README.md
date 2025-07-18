# Test Archive Directory

This directory contains test files that have been archived for the following reasons:

## Directory Structure

### `/debug/`
Contains debug and development test files that were used during development but are not part of the regular test suite:
- `test_bff_debug_internal.py` - BFF internal debugging
- `test_datatype_debug.py` - Data type debugging
- `test_final_debug.py` - Final debugging tests
- `test_label_debug.py` - Label handling debugging
- `test_terminus_debug.py` - TerminusDB connection debugging
- `test_multilingual_debug.py` - Multilingual functionality debugging
- `test_multilingual_debug_simple.py` - Simple multilingual debugging
- `test_url_alignment_debug.py` - URL alignment debugging

### `/fixes/`
Contains test files created to verify specific bug fixes. These have been archived after the fixes were validated:
- `test_bff_oms_integration_fix.py` - BFF-OMS integration fix verification
- `test_database_list_fix.py` - Database listing fix verification
- `test_id_generation_fix.py` - ID generation fix verification
- `test_id_generation_mismatch.py` - ID mismatch fix verification
- `test_language_issue.py` - Language issue fix verification
- `test_security_fix.py` - Security fix verification (⚠️ Keep monitoring for security)

### `/test_results/`
Contains JSON test result files from test runs. These should be periodically cleaned up.

## Restoration

If you need to restore any of these tests:
1. Copy the test file back to its original location
2. Verify all imports are still valid
3. Run the test to ensure it still works with current code
4. Update the test if necessary

## Maintenance

- Review archived tests quarterly
- Delete test result JSON files older than 30 days
- Consider permanently deleting debug tests after 6 months
- Keep fix verification tests for at least 1 year for audit purposes

---
*Archived on: 2025-07-18*