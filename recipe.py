import base64
from io import BytesIO
import re
from html import escape as escape_html
from urllib.parse import urljoin

import requests
import yaml
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from dotenv import load_dotenv
import os

load_dotenv()

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GITHUB_OWNER = "natakazakova"
GITHUB_REPO = "sister-cooking"
GITHUB_BRANCH = "main"
GITHUB_API = "https://api.github.com"
SITE_URL = "https://sister.cooking"
EXCLUDED_CATEGORIES = {"blog"}


def parse_recipe_markdown(markdown, path):
    front_matter = {}
    body = markdown

    if markdown.startswith("---"):
        parts = markdown.split("---", 2)
        if len(parts) == 3:
            front_matter = yaml.safe_load(parts[1]) or {}
            body = parts[2]

    title_match = re.search(r"^#\s+(.+)$", body, re.MULTILINE)
    image_match = re.search(r"!\[[^\]]*\]\(([^)]+)\)", body)
    description_match = re.search(
        r"</figure>\s*(.*?)\s*^##\s+Инвентарь",
        body,
        re.DOTALL | re.MULTILINE,
    )
    recipe_directory = path.rsplit("/", 1)[0]

    image_url = None
    if image_match:
        image_url = urljoin(
            f"{SITE_URL}/{recipe_directory}/",
            image_match.group(1),
        )

    return {
        "title": title_match.group(1).strip() if title_match else "",
        "description": (
            description_match.group(1).strip()
            if description_match
            else ""
        ),
        "image": image_url,
    }


def description_to_html(description, recipe_path):
    parts = []
    last_end = 0
    recipe_directory = recipe_path.rsplit("/", 1)[0]

    for match in re.finditer(r"\[([^]]+)\]\(([^)]+)\)", description):
        parts.append(escape_html(description[last_end:match.start()]))

        link_target = match.group(2)
        link_url = urljoin(
            f"{SITE_URL}/{recipe_directory}/",
            link_target,
        )
        if link_url.endswith(".md"):
            link_url = f"{link_url[:-3]}/"
        separator = "&" if "?" in link_url else "?"
        link_url = f"{link_url}{separator}utm_from=tgbot"

        parts.append(
            f'<a href="{escape_html(link_url)}">'
            f"{escape_html(match.group(1))}</a>"
        )
        last_end = match.end()

    parts.append(escape_html(description[last_end:]))
    return "".join(parts)


def github_headers():
    return {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def get_github_file(path):
    url = f"{GITHUB_API}/repos/{GITHUB_OWNER}/{GITHUB_REPO}/contents/{path}"
    response = requests.get(
        url,
        headers=github_headers(),
        params={"ref": GITHUB_BRANCH},
    )
    response.raise_for_status()
    data = response.json()
    return base64.b64decode(data["content"]).decode("utf-8")


def get_image_file(url):
    response = requests.get(url, timeout=30)
    response.raise_for_status()

    image_file = BytesIO(response.content)
    image_file.name = url.rsplit("/", 1)[-1]
    return image_file


def get_mkdocs_config():
    content = get_github_file("mkdocs.yml")
    navigation_marker = "# Navigation"

    if navigation_marker not in content:
        raise ValueError("Could not find the Navigation section in mkdocs.yml.")

    navigation = content.split(navigation_marker, 1)[1]
    return yaml.safe_load(navigation) or {}


def flatten_nav_items(items):
    paths = []

    for item in items or []:
        if isinstance(item, str) and item.endswith(".md"):
            paths.append(item)
        elif isinstance(item, dict):
            for nested_items in item.values():
                paths.extend(flatten_nav_items(nested_items))

    return paths


def parse_mkdocs_categories(config):
    categories = []

    for entry in config.get("nav", []):
        if not isinstance(entry, dict) or len(entry) != 1:
            continue

        title, items = next(iter(entry.items()))
        paths = flatten_nav_items(items)
        index_path = next(
            (path for path in paths if path.endswith("/index.md")),
            None,
        )

        if not index_path:
            continue

        category = index_path.split("/", 1)[0]
        if category in EXCLUDED_CATEGORIES:
            continue

        categories.append({
            "title": title,
            "category": category,
            "index_path": f"docs/{index_path}",
            "recipe_paths": [path for path in paths if path != index_path],
        })

    return categories


def recipe_title_map(index_content):
    return {
        path.split("/")[-1]: title
        for title, path in re.findall(
            r"\[([^\]]+)\]\(([^)]+\.md)\)",
            index_content,
        )
    }


def get_category(category_name):
    categories = parse_mkdocs_categories(get_mkdocs_config())
    return next(
        item for item in categories
        if item["category"] == category_name
    )


def category_keyboard(category):
    titles = recipe_title_map(get_github_file(category["index_path"]))
    keyboard = []

    for path in category["recipe_paths"]:
        filename = path.split("/")[-1]
        title = titles.get(
            filename,
            filename.removesuffix(".md").replace("-", " ").title(),
        )
        keyboard.append([
            InlineKeyboardButton(title, callback_data=f"recipe:{path}")
        ])

    return keyboard


async def send_category_recipes(message, category_name):
    category = get_category(category_name)

    if not category["recipe_paths"]:
        await message.reply_text("В этой категории рецепты не найдены.")
        return

    await message.reply_text(
        f"🍳 Рецепты: {category['title']}",
        reply_markup=InlineKeyboardMarkup(category_keyboard(category)),
    )


async def recipes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        categories = parse_mkdocs_categories(get_mkdocs_config())
    except Exception as error:
        await update.message.reply_text(f"Не удалось получить список категорий:\n{error}")
        return

    if not categories:
        await update.message.reply_text("Категории не найдены.")
        return

    keyboard = [
        [InlineKeyboardButton(
            category["title"],
            callback_data=f"category:{category['category']}",
        )]
        for category in categories
    ]
    await update.message.reply_text(
        "🍳 Выберите категорию:",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def show_category(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    category_name = query.data.replace("category:", "", 1)

    try:
        await send_category_recipes(query.message, category_name)
    except Exception as error:
        await query.message.reply_text(f"Не удалось получить список рецептов:\n\n{error}")
        return


async def back_to_category(update: Update, context: ContextTypes.DEFAULT_TYPE):
    category_name = context.user_data.get("last_category")

    if not category_name:
        await update.message.reply_text(
            "Сначала выберите категорию и рецепт."
        )
        return

    try:
        await send_category_recipes(update.message, category_name)
    except Exception as error:
        await update.message.reply_text(
            f"Не удалось получить список рецептов:\n\n{error}"
        )


async def show_recipe(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    path = query.data.replace("recipe:", "", 1)
    context.user_data["last_category"] = path.split("/", 1)[0]
    page_url = f"{SITE_URL}/{path[:-3]}/?utm_from=tgbot"

    try:
        recipe = parse_recipe_markdown(
            get_github_file(f"docs/{path}"),
            path,
        )
    except Exception as error:
        await query.message.reply_text(f"Не удалось открыть рецепт:\n\n{error}")
        return

    caption = "\n\n".join([
        f"<b>{escape_html(recipe['title'])}</b>",
        description_to_html(recipe["description"], path),
        f'<a href="{escape_html(page_url)}">Рецепт на сайте</a>',
    ])

    if recipe["image"]:
        try:
            await query.message.reply_photo(
                photo=get_image_file(recipe["image"]),
                caption=caption,
                parse_mode="HTML",
            )
        except Exception as error:
            print(f"Could not send image: {error}")
    else:
        await query.message.reply_text(
            caption,
            parse_mode="HTML",
            disable_web_page_preview=True,
        )


def split_message(text, max_length=4000):
    if len(text) <= max_length:
        return [text]

    chunks = []
    current = ""
    for line in text.split("\n"):
        if len(current) + len(line) + 1 > max_length:
            if current:
                chunks.append(current)
            if len(line) > max_length:
                chunks.extend(
                    line[index:index + max_length]
                    for index in range(0, len(line), max_length)
                )
                current = ""
            else:
                current = line
        else:
            if current:
                current += "\n"
            current += line

    if current:
        chunks.append(current)
    return chunks
