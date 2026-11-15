import os
import json
import time

from dotenv import load_dotenv
from openai import OpenAI

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException,
    NoSuchElementException,
    StaleElementReferenceException
)

# ==========================================
# CONFIGURATION
# ==========================================

load_dotenv()

FORM_URL = "https://docs.google.com/forms/d/e/YOUR_FORM_ID/viewform"

# Persistent Chrome profile
CHROME_PROFILE = os.path.abspath("./chrome_profile")

# Set True only when you want to submit
SUBMIT_FORM = False

# Information the LLM can use to answer questions
USER_CONTEXT = """
I am a computer science student.
I am interested in software engineering, competitive programming,
data structures, algorithms, and backend development.

Replace this with your actual background, preferences, and other
information relevant to the form.
"""

client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY"),
    # Optional OpenAI-compatible endpoint:
    # base_url="https://your-provider.com/v1"
)

MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")


# ==========================================
# SELENIUM INITIALIZATION
# ==========================================

def initialize_browser():

    options = Options()

    options.add_argument(f"--user-data-dir={CHROME_PROFILE}")
    options.add_argument("--start-maximized")

    driver = webdriver.Chrome(options=options)

    return driver


# ==========================================
# GOOGLE AUTHENTICATION
# ==========================================

def handle_authentication(driver):

    print("\nChecking Google authentication...")

    if "accounts.google.com" in driver.current_url:

        print("Google login required.")
        print("Please log in manually in the Chrome window.")
        print("Complete any 2FA verification if required.")

        WebDriverWait(driver, 300).until(
            lambda d: "accounts.google.com" not in d.current_url
        )

        print("Authentication completed.")

    # Wait for the Google Form to load
    WebDriverWait(driver, 60).until(
        EC.presence_of_element_located(
            (By.CSS_SELECTOR, 'form')
        )
    )

    time.sleep(2)


# ==========================================
# EXTRACT FORM QUESTIONS
# ==========================================

def extract_questions(driver):

    questions = []

    question_elements = driver.find_elements(
        By.CSS_SELECTOR,
        'div[role="listitem"]'
    )

    for index, element in enumerate(question_elements):

        try:

            title_element = element.find_element(
                By.CSS_SELECTOR,
                '.M7eMe'
            )

            question_text = title_element.text.strip()

            if not question_text:
                continue

            # Detect question type
            question_type = "unknown"
            options = []

            if element.find_elements(
                By.CSS_SELECTOR, 'div[role="radio"]'
            ):

                question_type = "radio"

                options = [
                    x.get_attribute("aria-label")
                    for x in element.find_elements(
                        By.CSS_SELECTOR, 'div[role="radio"]'
                    )
                ]

            elif element.find_elements(
                By.CSS_SELECTOR, 'div[role="checkbox"]'
            ):

                question_type = "checkbox"

                options = [
                    x.get_attribute("aria-label")
                    for x in element.find_elements(
                        By.CSS_SELECTOR, 'div[role="checkbox"]'
                    )
                ]

            elif element.find_elements(
                By.CSS_SELECTOR, 'div[role="listbox"]'
            ):

                question_type = "dropdown"

                dropdown = element.find_element(
                    By.CSS_SELECTOR, 'div[role="listbox"]'
                )

                # Open dropdown to inspect available options
                dropdown.click()
                time.sleep(0.3)

                options = [
                    x.text.strip()
                    for x in driver.find_elements(
                        By.CSS_SELECTOR, 'div[role="option"]'
                    )
                    if x.text.strip()
                ]

                # Close dropdown
                dropdown.click()

            elif element.find_elements(
                By.CSS_SELECTOR, 'textarea'
            ):

                question_type = "paragraph"

            elif element.find_elements(
                By.CSS_SELECTOR, 'input[type="text"]'
            ):

                question_type = "short_answer"

            elif element.find_elements(
                By.CSS_SELECTOR, 'input[type="date"]'
            ):

                question_type = "date"

            questions.append({
                "index": index,
                "question": question_text,
                "type": question_type,
                "options": options
            })

        except (
            NoSuchElementException,
            StaleElementReferenceException
        ):
            continue

    return questions


# ==========================================
# GET ANSWERS FROM LLM
# ==========================================

def generate_answers(questions):

    prompt = f"""
You are an assistant that fills out Google Forms.

Answer the following questions using the supplied user context.

USER CONTEXT:
{USER_CONTEXT}

QUESTIONS:
{json.dumps(questions, indent=2)}

INSTRUCTIONS:

1. Return one answer for each question.
2. For radio and dropdown questions, return exactly one
   answer matching an available option.
3. For checkbox questions, return a list of matching options.
4. For short_answer and paragraph questions, return strings.
5. Never invent personal information.
6. If you cannot determine an answer from the context,
   use an empty string or an empty list.
7. Keep answers relevant and concise.
8. Return valid JSON only.

EXPECTED FORMAT:

{{
    "answers": [
        {{
            "index": 0,
            "answer": "Example answer"
        }}
    ]
}}
"""

    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {
                "role": "system",
                "content": "You generate accurate, structured Google Form answers."
            },
            {
                "role": "user",
                "content": prompt
            }
        ],
        response_format={
            "type": "json_object"
        },
        temperature=0.2
    )

    result = json.loads(
        response.choices[0].message.content
    )

    return result["answers"]


# ==========================================
# FILL TEXT FIELDS
# ==========================================

def fill_text_field(element, answer):

    if not answer:
        return

    fields = element.find_elements(
        By.CSS_SELECTOR,
        'textarea, input[type="text"]'
    )

    if not fields:
        return

    field = fields[0]

    field.clear()
    field.send_keys(str(answer))


# ==========================================
# FILL RADIO BUTTONS
# ==========================================

def fill_radio(element, answer):

    if not answer:
        return

    options = element.find_elements(
        By.CSS_SELECTOR,
        'div[role="radio"]'
    )

    for option in options:

        label = option.get_attribute("aria-label")

        if label and label.strip().lower() == str(answer).strip().lower():

            if option.get_attribute("aria-checked") != "true":
                option.click()

            return


# ==========================================
# FILL CHECKBOXES
# ==========================================

def fill_checkboxes(element, answers):

    if not isinstance(answers, list):
        answers = [answers]

    for option in element.find_elements(
        By.CSS_SELECTOR,
        'div[role="checkbox"]'
    ):

        label = option.get_attribute("aria-label")

        if not label:
            continue

        should_select = any(
            label.strip().lower() == str(answer).strip().lower()
            for answer in answers
        )

        currently_selected = (
            option.get_attribute("aria-checked") == "true"
        )

        if should_select and not currently_selected:
            option.click()


# ==========================================
# FILL DROPDOWN
# ==========================================

def fill_dropdown(element, answer):

    if not answer:
        return

    dropdown = element.find_element(
        By.CSS_SELECTOR,
        'div[role="listbox"]'
    )

    dropdown.click()

    options = WebDriverWait(
        driver, 5
    ).until(
        lambda d: d.find_elements(
            By.CSS_SELECTOR,
            'div[role="option"]'
        )
    )

    for option in options:

        if option.text.strip().lower() == str(answer).strip().lower():

            option.click()
            return

    # Close dropdown if no matching option
    dropdown.click()


# ==========================================
# MAIN FORM FILLING LOGIC
# ==========================================

def fill_form(driver, questions, answers):

    answer_map = {
        item["index"]: item["answer"]
        for item in answers
    }

    elements = driver.find_elements(
        By.CSS_SELECTOR,
        'div[role="listitem"]'
    )

    for question in questions:

        index = question["index"]
        question_type = question["type"]

        answer = answer_map.get(index)

        if answer is None:
            continue

        try:

            element = elements[index]

            print(
                f"\nQuestion: {question['question']}"
            )

            print(f"Answer: {answer}")

            if question_type in ("short_answer", "paragraph"):

                fill_text_field(element, answer)

            elif question_type == "radio":

                fill_radio(element, answer)

            elif question_type == "checkbox":

                fill_checkboxes(element, answer)

            elif question_type == "dropdown":

                fill_dropdown(element, answer)

            else:

                print("Unsupported field type. Skipping.")

            time.sleep(0.2)

        except Exception as error:

            print(
                f"Failed to fill question {index}: {error}"
            )


# ==========================================
# SUBMIT FORM
# ==========================================

def submit_form(driver):

    print("\nSubmitting form...")

    submit_button = WebDriverWait(
        driver, 10
    ).until(
        EC.element_to_be_clickable(
            (
                By.XPATH,
                '//div[@role="button"]'
                '[.//span[contains(text(), "Submit")]]'
            )
        )
    )

    submit_button.click()

    print("Submit button clicked.")

    time.sleep(3)

    print("Current URL:", driver.current_url)


# ==========================================
# MAIN
# ==========================================

def main():

    global driver

    driver = initialize_browser()

    try:

        # Open Google Form
        driver.get(FORM_URL)

        # Authenticate if necessary
        handle_authentication(driver)

        # Extract questions
        print("\nExtracting questions...")

        questions = extract_questions(driver)

        print(
            json.dumps(questions, indent=2)
        )

        if not questions:
            print("No questions found.")
            return

        # Ask LLM
        print("\nGenerating answers using LLM...")

        answers = generate_answers(questions)

        print("\nGenerated answers:")
        print(json.dumps(answers, indent=2))

        # Fill form
        print("\nFilling form...")

        fill_form(
            driver,
            questions,
            answers
        )

        print("\nForm filling completed.")

        # Submit only when explicitly enabled
        if SUBMIT_FORM:

            input(
                "Review the filled form. Press ENTER to submit..."
            )

            submit_form(driver)

        else:

            print(
                "\nForm NOT submitted. "
                "Review the answers in Chrome."
            )

        input("\nPress ENTER to close browser...")

    finally:

        driver.quit()


if __name__ == "__main__":
    main()