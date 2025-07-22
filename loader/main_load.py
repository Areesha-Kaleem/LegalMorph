from loader.load_json import load_json, txt_json_db

def load():
    print("Loading all the files in database...")
    final_json = "D:\\LegalMorph\\final_json"
    custom_json = "D:\\LegalMorph\\custom_json"
    base_json = "D:\\LegalMorph\\base_json"
    raw_dir = "D:\\LegalMorph\\data"
    summarized_dir = "D:\\LegalMorph\\summarized_text"
    f_name = "final"
    f_collection = "LegalCases"
    c_name = "Custom"
    c_collection = "CustomLegalCases"
    b_name = "Base"
    b_collection = "BaseLegalCases"
    s_name = "Summarized"
    s_collection = "SumLegalCases"
    r_name = "Raw"
    r_collection = "Legal_raw_cases"
    print("Loading Raw json in DB...")
    txt_json_db(raw_dir, r_name, r_collection)
    print("Loading Summarized json for long cases in DB...")
    txt_json_db(summarized_dir, s_name, s_collection)
    print("loading custom json...")
    load_json(custom_json, c_name, c_collection)
    print("loading base json...")
    load_json(base_json, b_name, b_collection)
    print("loading Final json...")
    load_json(final_json, f_name, f_collection)

# load()
