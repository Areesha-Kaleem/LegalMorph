from loader.load_json import load_json, txt_json_db

def load():
    print("Loading all the files in database...")
    final_json = "D:\\LegalMorph\\final_json"
    custom_json = "D:\\LegalMorph\\custom_json"
    base_json = "D:\\LegalMorph\\base_json"
    f_name = "final"
    f_collection = "LegalCases"
    c_name = "Custom"
    c_collection = "CustomLegalCases"
    b_name = "Base"
    b_collection = "BaseLegalCases"
    print("Loading Raw json in DB...")
    txt_json_db()
    print("loading custom json...")
    load_json(custom_json, c_name, c_collection)
    print("loading base json...")
    load_json(base_json, b_name, b_collection)
    print("loading Final json...")
    load_json(final_json, f_name, f_collection)

# load()