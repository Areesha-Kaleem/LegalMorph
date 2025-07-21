from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import StaleElementReferenceException
from extractor.text_cleaner import extract_clean_text_from_html
import time
import traceback
import re
import os

def extract_case_data(driver, title, index):
    WebDriverWait(driver, 10).until(lambda d: len(d.window_handles) > 1)
    driver.switch_to.window(driver.window_handles[1])

    WebDriverWait(driver, 20).until(
        EC.presence_of_element_located(
            (By.XPATH, "//p[contains(@class, 'text-2xl') and contains(@class, 'font-bold')]")
        )
    )

    html = driver.page_source
    text = extract_clean_text_from_html(html)

    # ✅ Sanitize title to make it a valid filename
    safe_title = re.sub(r'[\\/*?:"<>|\r\n]', "_", title).strip()
    filename = f"{safe_title}.txt"

    # ✅ Define full path inside data directory
    data_dir = "D:/LegalMorph/test_data"  # or just "data" if it's relative
    os.makedirs(data_dir, exist_ok=True)
    file_path = os.path.join(data_dir, filename)

    try:
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(text)
        print(f"✅ Saved: {file_path}")
    except Exception as e:
        print(f"⚠️ Failed to save file for '{title}': {e}")

    driver.close()
    driver.switch_to.window(driver.window_handles[0])
    time.sleep(2)



def scrape_cases_from_eastlaw(case_limit):
    domain = "eastlaw.pk"
    options = Options()
    options.add_experimental_option("detach", True)
    driver = webdriver.Chrome(options=options)

    login_url = f"https://{domain}/"
    driver.get(login_url)
    print("🔐 Please log in manually in the Chrome window.")
    input("✅ After logging in completely, press ENTER to continue...")
    time.sleep(5)

    print("⏳ Waiting for sidebar to load and clicking on items...")
    sidebar_keywords = ["Judgments", "judges", "courts"]
    visited_sections = set()
    total_cases_scraped = 0

    for keyword in sidebar_keywords:
        if keyword in visited_sections or total_cases_scraped >= case_limit:
            continue

        xpath_variants = [
            f"//p[contains(text(), '{keyword}')]",
            f"//*[contains(text(), '{keyword}')]",
            f"//*[@aria-label='{keyword}']"
        ]
        sidebar_clicked = False
        for xpath in xpath_variants:
            elements = driver.find_elements(By.XPATH, xpath)
            for el in elements:
                try:
                    driver.execute_script("arguments[0].click();", el)
                    time.sleep(3)
                    print(f"✅ Clicked on: {keyword}")
                    sidebar_clicked = True
                    break
                except:
                    continue
            if sidebar_clicked:
                break

        if not sidebar_clicked:
            print(f"❌ Could not find or click '{keyword}' in sidebar.")
            continue

        visited_sections.add(keyword)
        if keyword == "Judgments" and total_cases_scraped < case_limit:
            try:
                print("⏳ Collecting case list...")
                cases = WebDriverWait(driver, 25).until(
                    EC.presence_of_all_elements_located(
                        (By.XPATH, "//div[contains(@aria-label, 'vs')]/div[contains(@class, 'action')]")
                    )
                )

                if len(cases) < case_limit:
                    print(f"⚠️ Only {len(cases)} cases found. Adjusting case_limit to {len(cases)}.")
                    case_limit = len(cases)

                for i in range(case_limit):
                    try:
                        print(f"\n⏳ Processing case {i + 1}...")

                        # Refresh list if needed (in case of DOM changes)
                        cases = driver.find_elements(By.XPATH,
                                                     "//div[contains(@aria-label, 'vs')]/div[contains(@class, 'action')]")

                        icon = cases[i]
                        title = icon.find_element(By.XPATH, "./parent::div").get_attribute("aria-label")

                        driver.execute_script("arguments[0].scrollIntoView();", icon)
                        driver.execute_script("arguments[0].click();", icon)
                        extract_case_data(driver, title, total_cases_scraped)
                        total_cases_scraped += 1
                    except Exception as e:
                        print(f"⚠️ Skipped case due to error: {e}")
                        traceback.print_exc()
                        if len(driver.window_handles) > 1:
                            driver.close()
                        driver.switch_to.window(driver.window_handles[0])
                        continue

            except Exception as outer_error:
                print(f"🚨 Unexpected issue: {outer_error}")
                traceback.print_exc()
            total_cases_scraped = 0

        # elif keyword == "judges":
        #     try:
        #         visited_judge = set()
        #         print("👩‍⚖️ Scraping Judges dropdown list...")
        #
        #         judge_dropdown_button = WebDriverWait(driver, 10).until(
        #
        #             EC.element_to_be_clickable((By.XPATH,
        #
        #                                         "//input[@placeholder='Select Judge']/following-sibling::div//button[@aria-label='Open']"))
        #
        #         )
        #
        #         driver.execute_script("arguments[0].click();", judge_dropdown_button)
        #
        #         time.sleep(1)
        #
        #         judge_list_items = WebDriverWait(driver, 10).until(
        #
        #             EC.presence_of_all_elements_located((By.XPATH, "//li[@role='option']"))
        #
        #         )
        #
        #         for judge_item in range(len(judge_list_items)):
        #             judge_name = ""
        #             if len(visited_judge) == 0:
        #                 element = judge_list_items[judge_item]
        #                 judge_name = element.text.strip()
        #                 print(f"➡️ Selecting Judge: {judge_name}")
        #                 driver.execute_script("arguments[0].click();", element)
        #                 time.sleep(2)
        #             else:
        #                 judge_dropdown_button = WebDriverWait(driver, 10).until(
        #
        #                     EC.element_to_be_clickable((By.XPATH,
        #
        #                                                 "//input[@placeholder='Select Judge']/following-sibling::div//button[@aria-label='Open']"))
        #
        #                 )
        #
        #                 driver.execute_script("arguments[0].click();", judge_dropdown_button)
        #
        #                 time.sleep(1)
        #                 fresh_judges = WebDriverWait(driver, 10).until(
        #                     EC.presence_of_all_elements_located((By.XPATH, "//li[@role='option']"))
        #                 )
        #                 for i in range(len(fresh_judges)):
        #                     try:
        #                         # REFRESH the list every time to avoid stale refs
        #                         fresh_judges = WebDriverWait(driver, 10).until(
        #                             EC.presence_of_all_elements_located((By.XPATH, "//li[@role='option']"))
        #                         )
        #                         item = fresh_judges[i]
        #                         name = item.text.strip()
        #
        #                         if name not in visited_judge:
        #                             print(f"➡️ Selecting Judge: {name}")
        #                             driver.execute_script("arguments[0].click();", item)
        #                             judge_name = name
        #                             visited_judge.add(name)  # ✅ Track so we don't repeat
        #                             break
        #
        #                     except StaleElementReferenceException:
        #                         print("♻️ Stale judge element, retrying...")
        #                         time.sleep(1)
        #             for _ in range(10):
        #
        #                 profile_input = driver.find_element(By.XPATH, "//input[@placeholder='Select Profile']")
        #
        #                 if not profile_input.get_attribute("disabled"):
        #                     break
        #
        #                 time.sleep(1)
        #
        #             else:
        #
        #                 print("❌ 'Select Profile' still disabled.")
        #
        #                 continue
        #
        #             court_dropdown_button = WebDriverWait(driver, 10).until(
        #
        #                 EC.element_to_be_clickable((By.XPATH,
        #
        #                                             "//input[@placeholder='Select Profile']/following::button[@aria-label='Open']"))
        #
        #             )
        #
        #             driver.execute_script("arguments[0].click();", court_dropdown_button)
        #
        #             time.sleep(1)
        #
        #             court_list_items = WebDriverWait(driver, 10).until(
        #                 EC.presence_of_all_elements_located((By.XPATH, "//li[@role='option']"))
        #             )
        #             visited_court = set()
        #             for court_item in range(len(court_list_items)):
        #                 if len(visited_court) == 0:
        #                     element = court_list_items[court_item]
        #                     court_name = element.text.strip()
        #                     print(f"➡️ Selecting court: {court_name}")
        #                     driver.execute_script("arguments[0].click();", element)
        #                     print(f"→ Exploring Judge-Court: {judge_name} | {court_name}")
        #                     time.sleep(2)
        #                     visited_court.add(court_name)
        #                 else:
        #                     court_dropdown_button = WebDriverWait(driver, 10).until(
        #
        #                         EC.element_to_be_clickable((By.XPATH,
        #
        #                                                     "//input[@placeholder='Select Profile']/following::button[@aria-label='Open']"))
        #
        #                     )
        #
        #                     driver.execute_script("arguments[0].click();", court_dropdown_button)
        #
        #                     time.sleep(1)
        #
        #                     fresh_items = WebDriverWait(driver, 10).until(
        #                         EC.presence_of_all_elements_located((By.XPATH, "//li[@role='option']"))
        #                     )
        #                     for item in fresh_items:
        #                         if item.text.strip() not in visited_court:
        #                             court_name = item.text.strip()
        #                             print(f"→ Exploring Judge-Court: {judge_name} | {court_name}")
        #                             driver.execute_script("arguments[0].click();", item)
        #                             time.sleep(2)
        #                             visited_court.add(court_name)
        #                             break
        #                 # Scrape All tab
        #
        #                 try:
        #
        #                     print(f"\n🗂️ Scraping tab: All")
        #
        #                     tab_xpath = "//span[normalize-space(text())='All']"
        #
        #                     tab = WebDriverWait(driver, 15).until(
        #
        #                         EC.element_to_be_clickable((By.XPATH, tab_xpath))
        #
        #                     )
        #
        #                     driver.execute_script("arguments[0].click();", tab)
        #
        #                     time.sleep(10)
        #
        #                     case_elements = driver.find_elements(By.XPATH,
        #
        #                                                          "//div[contains(@aria-label, 'vs')]/div[contains(@class, 'action')]")
        #
        #                     scraped_count = 0
        #                     limiter = case_limit
        #                     if limiter > len(case_elements):
        #                         limiter = len(case_elements)
        #                         if limiter == 0:
        #                             print("No case data found under this tab")
        #                     for icon in case_elements:
        #                         if scraped_count >= limiter:
        #                             break
        #
        #                         try:
        #
        #                             title = icon.find_element(By.XPATH, "./parent::div").get_attribute("aria-label")
        #
        #                             driver.execute_script("arguments[0].scrollIntoView();", icon)
        #
        #                             driver.execute_script("arguments[0].click();", icon)
        #
        #                             extract_case_data(driver, title, scraped_count)
        #
        #                             scraped_count += 1
        #
        #                         except Exception as e:
        #
        #                             print(f"⚠️ Skipped case due to error: {e}")
        #
        #                             traceback.print_exc()
        #
        #                             if len(driver.window_handles) > 1:
        #                                 driver.close()
        #
        #                             driver.switch_to.window(driver.window_handles[0])
        #
        #                 except Exception as e:
        #
        #                     print(f"⚠️ Failed to process 'All' tab: {e}")
        #
        #                 # Scrape Single Bench
        #
        #                 try:
        #
        #                     print(f"\n🗂️ Scraping tab: Single Bench")
        #
        #                     tab_xpath = "//span[normalize-space(text())='Single Bench']"
        #
        #                     tab = WebDriverWait(driver, 15).until(
        #
        #                         EC.element_to_be_clickable((By.XPATH, tab_xpath))
        #
        #                     )
        #
        #                     driver.execute_script("arguments[0].click();", tab)
        #
        #                     time.sleep(10)
        #
        #                     case_elements = driver.find_elements(By.XPATH,
        #
        #                                                          "//div[contains(@aria-label, 'vs')]/div[contains(@class, 'action')]")
        #
        #                     scraped_count = 0
        #                     limiter = case_limit
        #                     if limiter > len(case_elements):
        #                         limiter = len(case_elements)
        #                         if limiter == 0:
        #                             print("No case data found under this tab")
        #                     for icon in case_elements:
        #                         if scraped_count >= limiter:
        #                             break
        #
        #                         try:
        #
        #                             title = icon.find_element(By.XPATH, "./parent::div").get_attribute("aria-label")
        #
        #                             driver.execute_script("arguments[0].scrollIntoView();", icon)
        #
        #                             driver.execute_script("arguments[0].click();", icon)
        #
        #                             extract_case_data(driver, title, scraped_count)
        #
        #                             scraped_count += 1
        #
        #                         except Exception as e:
        #
        #                             print(f"⚠️ Skipped case due to error: {e}")
        #
        #                             traceback.print_exc()
        #
        #                             if len(driver.window_handles) > 1:
        #                                 driver.close()
        #
        #                             driver.switch_to.window(driver.window_handles[0])
        #
        #                 except Exception as e:
        #
        #                     print(f"⚠️ Failed to process 'Single Bench' tab: {e}")
        #
        #                 # Placeholder for Large Bench routing
        #
        #                 try:
        #
        #                     print(f"\n🗂️ Skipping 'D.B. or Larger Bench' for now (placeholder)")
        #
        #                 except Exception as e:
        #
        #                     print(f"⚠️ Failed to process 'D.B. or Larger Bench' tab: {e}")
        #
        #
        #                 try:
        #
        #                     all_tab_xpath = "//span[normalize-space(text())='All']"
        #
        #                     all_tab = WebDriverWait(driver, 5).until(
        #
        #                         EC.element_to_be_clickable((By.XPATH, all_tab_xpath))
        #
        #                     )
        #
        #                     driver.execute_script("arguments[0].click();", all_tab)
        #
        #                     time.sleep(15)
        #
        #                 except:
        #
        #                     print("⚠️ Failed to return to All tab.")
        #
        #             visited_judge.add(judge_name)
        #     except Exception as e:
        #
        #         print(f"⚠️ Judges section failed: {e}")
        #
        #         traceback.print_exc()
        #
        #
        # elif keyword == "courts":
        #
        #     try:
        #
        #         visited_courts = set()
        #         court_name = ""
        #
        #         print("🏛️ Scraping Courts dropdown list...")
        #
        #         court_dropdown_button = WebDriverWait(driver, 10).until(
        #
        #             EC.element_to_be_clickable((By.XPATH,
        #
        #                                         "//input[@placeholder='Select Court']/following-sibling::div//button[@aria-label='Open']"))
        #
        #         )
        #
        #         driver.execute_script("arguments[0].click();", court_dropdown_button)
        #
        #         time.sleep(5)
        #
        #         court_list_items = WebDriverWait(driver, 15).until(
        #
        #             EC.presence_of_all_elements_located((By.XPATH, "//li[@role='option']"))
        #
        #         )
        #
        #         for i in range(len(court_list_items)):
        #
        #             if len(visited_courts) == 0:
        #
        #                 element = court_list_items[i]
        #
        #                 court_name = element.text.strip()
        #
        #                 print(f"➡️ Selecting court: {court_name}")
        #
        #                 driver.execute_script("arguments[0].click();", element)
        #
        #                 time.sleep(5)
        #
        #                 visited_courts.add(court_name)
        #
        #             else:
        #
        #                 court_dropdown_button = WebDriverWait(driver, 15).until(
        #
        #                     EC.element_to_be_clickable((By.XPATH,
        #
        #                                                 "//input[@placeholder='Select Court']/following::button[@aria-label='Open']"))
        #
        #                 )
        #
        #                 driver.execute_script("arguments[0].click();", court_dropdown_button)
        #
        #                 time.sleep(1)
        #
        #                 fresh_courts = WebDriverWait(driver, 15).until(
        #
        #                     EC.presence_of_all_elements_located((By.XPATH, "//li[@role='option']"))
        #
        #                 )
        #
        #                 for court in fresh_courts:
        #
        #                     name = court.text.strip()
        #
        #                     if name not in visited_courts:
        #                         court_name = name
        #
        #                         driver.execute_script("arguments[0].click();", court)
        #
        #                         time.sleep(5)
        #
        #                         visited_courts.add(name)
        #
        #                         break
        #
        #             # 🔽 Judge Dropdown after court selected
        #
        #             visited_judges = set()
        #             judge_name = " "
        #
        #             judge_dropdown_button = WebDriverWait(driver, 15).until(
        #
        #                 EC.element_to_be_clickable((By.XPATH,
        #
        #                                             "//input[@placeholder='Select Judge']/following-sibling::div//button[@aria-label='Open']"))
        #
        #             )
        #
        #             driver.execute_script("arguments[0].click();", judge_dropdown_button)
        #
        #             time.sleep(1)
        #
        #             judge_list_items = WebDriverWait(driver, 15).until(
        #
        #                 EC.presence_of_all_elements_located((By.XPATH, "//li[@role='option']"))
        #
        #             )
        #
        #             for j in range(len(judge_list_items)):
        #
        #                 if len(visited_judges) == 0:
        #
        #                     element = judge_list_items[j]
        #
        #                     judge_name = element.text.strip()
        #
        #                     print(f"➡️ Selecting judge: {judge_name}")
        #
        #                     driver.execute_script("arguments[0].click();", element)
        #
        #                     visited_judges.add(judge_name)
        #
        #                     time.sleep(5)
        #
        #                 else:
        #
        #                     judge_dropdown_button = WebDriverWait(driver, 15).until(
        #
        #                         EC.element_to_be_clickable((By.XPATH,
        #
        #                                                     "//input[@placeholder='Select Judge']/following::button[@aria-label='Open']"))
        #
        #                     )
        #
        #                     driver.execute_script("arguments[0].click();", judge_dropdown_button)
        #
        #                     time.sleep(1)
        #
        #                     fresh_judges = WebDriverWait(driver, 15).until(
        #
        #                         EC.presence_of_all_elements_located((By.XPATH, "//li[@role='option']"))
        #
        #                     )
        #
        #                     for judge in fresh_judges:
        #
        #                         name = judge.text.strip()
        #
        #                         if name not in visited_judges:
        #                             judge_name = name
        #
        #                             print(f"➡️ Selecting judge: {judge_name}")
        #
        #                             driver.execute_script("arguments[0].click();", judge)
        #
        #                             visited_judges.add(name)
        #
        #                             time.sleep(5)
        #
        #                             break
        #
        #                 # ✅ Scrape cases for this Court-Judge pair
        #
        #                 print(f"→ Exploring Court-Judge: {court_name} | {judge_name}")
        #
        #                 case_elements = driver.find_elements(By.XPATH,
        #
        #                                                      "//div[contains(@aria-label, 'vs')]/div[contains(@class, 'action')]"
        #
        #                                                      )
        #
        #                 if not case_elements:
        #                     print("⚠️ No case data found.")
        #
        #                     continue
        #
        #                 for icon in case_elements[:case_limit]:
        #
        #                     try:
        #
        #                         title = icon.find_element(By.XPATH, "./parent::div").get_attribute("aria-label")
        #
        #                         driver.execute_script("arguments[0].scrollIntoView();", icon)
        #
        #                         driver.execute_script("arguments[0].click();", icon)
        #
        #                         extract_case_data(driver, title, case_limit)
        #
        #                     except Exception as e:
        #
        #                         print(f"⚠️ Skipped case due to error: {e}")
        #
        #                         traceback.print_exc()
        #
        #                         if len(driver.window_handles) > 1:
        #                             driver.close()
        #
        #                         driver.switch_to.window(driver.window_handles[0])
        #
        #
        #     except Exception as e:
        #
        #         print(f"⚠️ Courts section failed: {e}")
        #
        #         traceback.print_exc()

    print("\n🎯 Scraping finished.")
