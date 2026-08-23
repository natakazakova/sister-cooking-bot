import re
from datetime import date, datetime

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes
import yaml

from recipe import (
	SITE_URL,
	get_github_directory,
	get_github_file,
)


def format_blog_date(value):
	if not isinstance(value, (date, datetime)):
		return ""

	months = (
		"янв.", "февр.", "мар.", "апр.", "мая", "июн.",
		"июл.", "авг.", "сент.", "окт.", "нояб.", "дек.",
	)
	return f"{value.day} {months[value.month - 1]} {value.year} г."


def parse_blog_post(markdown, path):
	front_matter = {}
	if markdown.startswith("---"):
		parts = markdown.split("---", 2)
		if len(parts) == 3:
			front_matter = yaml.safe_load(parts[1]) or {}

	title_match = re.search(r"^#\s+(.+)$", markdown, re.MULTILINE)
	return {
		"title": front_matter.get("title") or (
			title_match.group(1).strip()
			if title_match
			else path.rsplit("/", 1)[-1].removesuffix(".md").replace("-", " ").title()
		),
		"date": format_blog_date(front_matter.get("date")),
		"date_value": front_matter.get("date"),
		"draft": front_matter.get("draft", False) is True,
		"path": path,
	}


def blog_keyboard(posts):
	return [[
		InlineKeyboardButton(
			post["title"],
			url=(
				f"{SITE_URL}/blog/"
				f"{post['path'].removeprefix('docs/blog/posts/')[:-3]}"
				"/?utm_from=tgbot"
			),
		)
	] for post in posts]


async def blog(update: Update, context: ContextTypes.DEFAULT_TYPE):
	try:
		files = get_github_directory("docs/blog/posts")
		posts = [
			parse_blog_post(
				get_github_file(item["path"]),
				item["path"],
			)
			for item in files
			if item.get("type") == "file" and item["name"].endswith(".md")
		]
		posts = [post for post in posts if not post["draft"]]
		posts.sort(key=lambda post: post["date_value"] or date.min, reverse=True)
	except Exception as error:
		await update.message.reply_text(f"Не удалось получить список публикаций:\n\n{error}")
		return

	if not posts:
		await update.message.reply_text("Публикации не найдены.")
		return

	post_details = "\n\n".join(
		f"<b>{post['title']}</b>\n{post['date']}"
		for post in posts
		if post["date"]
	)
	await update.message.reply_text(
		f"📝 Публикации в блоге:\n\n{post_details}",
		reply_markup=InlineKeyboardMarkup(blog_keyboard(posts)),
		parse_mode="HTML",
	)
