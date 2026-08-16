#!/usr/bin/env python3
"""
Command-line Interface for Technical Terms Translator (Chinese - English - Russian).
"""

import sys
import asyncio
import argparse
from typing import Optional

from translator.models import TechTerm, Language, TranslationOutput
from translator.engine import TerminologyEngine, TechTranslator
from translator.pinyin_helper import detect_language, get_pinyin


# ANSI Color Codes for terminal formatting
class Colors:
    HEADER = "\033[95m"
    BLUE = "\033[94m"
    CYAN = "\033[96m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    BOLD = "\033[1m"
    UNDERLINE = "\033[4m"
    DIM = "\033[2m"
    END = "\033[0m"


def format_term_card(term: TechTerm, show_definition: bool = True, show_examples: bool = True) -> str:
    """Format a single technical term card with colors and clean layout."""
    lines = []
    lines.append(f"{Colors.BOLD}{Colors.CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{Colors.END}")
    lines.append(f"{Colors.BOLD}🇬🇧 EN:{Colors.END} {Colors.GREEN}{term.en}{Colors.END}")
    lines.append(f"{Colors.BOLD}🇨🇳 ZH:{Colors.END} {Colors.YELLOW}{term.zh}{Colors.END} {Colors.DIM}(Pinyin: {term.pinyin}){Colors.END}" + (f" [{term.zh_trad}]" if term.zh_trad else ""))
    lines.append(f"{Colors.BOLD}🇷🇺 RU:{Colors.END} {Colors.BLUE}{term.ru}{Colors.END}")
    lines.append(f"{Colors.DIM}📁 Категория: {term.category}{Colors.END}")

    if show_definition:
        lines.append("")
        lines.append(f"{Colors.BOLD}📖 Определения / Definitions:{Colors.END}")
        if term.definition_ru:
            lines.append(f"  🇷🇺 {term.definition_ru}")
        if term.definition_en:
            lines.append(f"  🇬🇧 {term.definition_en}")
        if term.definition_zh:
            lines.append(f"  🇨🇳 {term.definition_zh}")

    if show_examples and term.examples:
        lines.append("")
        lines.append(f"{Colors.BOLD}💡 Примеры употребления / Examples:{Colors.END}")
        for ex in term.examples:
            lines.append(f"  🇬🇧 {ex.en}")
            lines.append(f"  🇨🇳 {ex.zh}" + (f" ({ex.pinyin})" if ex.pinyin else ""))
            lines.append(f"  🇷🇺 {ex.ru}")
            lines.append("")

    synonyms = []
    if term.synonyms_en:
        synonyms.append(f"EN: {', '.join(term.synonyms_en)}")
    if term.synonyms_zh:
        synonyms.append(f"ZH: {', '.join(term.synonyms_zh)}")
    if term.synonyms_ru:
        synonyms.append(f"RU: {', '.join(term.synonyms_ru)}")

    if synonyms:
        lines.append(f"{Colors.BOLD}🏷️  Синонимы:{Colors.END} {' | '.join(synonyms)}")

    if term.related_terms:
        lines.append(f"{Colors.BOLD}🔗 Связанные термины:{Colors.END} {', '.join(term.related_terms)}")

    lines.append(f"{Colors.BOLD}{Colors.CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{Colors.END}")
    return "\n".join(lines)


def format_translation_output(output: TranslationOutput) -> str:
    """Format full translation output."""
    lines = []
    det_lang = output.detected_lang.display_name_ru
    lines.append(f"{Colors.DIM}🔍 Запрос: '{output.query}' (Язык: {det_lang}){Colors.END}\n")

    if output.direct_match:
        lines.append(f"{Colors.BOLD}{Colors.GREEN}✓ Точное совпадение в словаре:{Colors.END}")
        lines.append(format_term_card(output.direct_match))
    elif output.search_results:
        lines.append(f"{Colors.BOLD}{Colors.YELLOW}⚡ Найденные термины в базе:{Colors.END}\n")
        for i, res in enumerate(output.search_results, 1):
            term = res.term
            lines.append(f"{Colors.BOLD}{i}. {term.en} ↔ {term.zh} ({term.pinyin}) ↔ {term.ru}{Colors.END} {Colors.DIM}[совпадение: {res.score*100:.0f}%]{Colors.END}")
            lines.append(f"   🇷🇺 {term.definition_ru}")
            lines.append("")
        lines.append(f"{Colors.DIM}Для подробного описания введите точное название термина.{Colors.END}")
    else:
        lines.append(f"{Colors.YELLOW}Термин не найден в локальной базе.{Colors.END}")

    if output.online_translations:
        lines.append(f"\n{Colors.BOLD}🌐 Онлайн-перевод:{Colors.END}")
        for lang, text in output.online_translations.items():
            flag = "🇬🇧" if lang == "en" else "🇷🇺" if lang == "ru" else "🇨🇳"
            lines.append(f"  {flag} {text}")

    if output.pinyin and not output.direct_match:
        lines.append(f"  🇨🇳 Pinyin: {output.pinyin}")

    return "\n".join(lines)


async def run_cli():
    parser = argparse.ArgumentParser(
        description="Переводчик технических терминов (Китайский - Английский - Русский)"
    )
    parser.add_argument("query", nargs="?", help="Термин для перевода или поиска")
    parser.add_argument("-c", "--category", help="Фильтр по категории (например, ai_ml, hardware)")
    parser.add_argument("--categories", action="store_true", help="Показать все категории")
    parser.add_argument("-r", "--random", type=int, const=1, nargs="?", help="Показать N случайных терминов")
    parser.add_argument("-i", "--interactive", action="store_true", help="Интерактивный режим")
    parser.add_argument("-q", "--quiz", action="store_true", help="Режим викторины / карточек")

    args = parser.parse_args()

    engine = TerminologyEngine()
    translator = TechTranslator(engine)

    # List categories
    if args.categories:
        print(f"\n{Colors.BOLD}📚 Доступные категории технических терминов:{Colors.END}\n")
        for cat in engine.get_all_categories():
            terms_count = len(engine.get_terms_by_category(cat.id))
            print(f" {cat.icon} {Colors.BOLD}{cat.id}{Colors.END} - {cat.name_ru} / {cat.name_en} / {cat.name_zh} ({terms_count} терминов)")
            print(f"    {Colors.DIM}{cat.description_ru}{Colors.END}\n")
        return

    # Random terms
    if args.random is not None:
        count = args.random or 1
        terms = engine.get_random_terms(count=count, category=args.category)
        print(f"\n{Colors.BOLD}🎲 Случайные термины ({len(terms)}):{Colors.END}\n")
        for term in terms:
            print(format_term_card(term))
            print()
        return

    # Single search query
    if args.query:
        output = await translator.translate(args.query, category=args.category)
        print(format_translation_output(output))
        return

    # Interactive Quiz Mode
    if args.quiz:
        await interactive_quiz(engine)
        return

    # Interactive REPL mode (default if no arguments)
    await interactive_repl(engine, translator)


async def interactive_quiz(engine: TerminologyEngine):
    """Interactive quiz / flashcards to practice technical vocabulary."""
    import random
    print(f"\n{Colors.BOLD}{Colors.GREEN}🧠 Викторина по техническим терминам (ZH - EN - RU){Colors.END}")
    print(f"{Colors.DIM}Введите 'q' или 'exit' для выхода в меню.{Colors.END}\n")

    score = 0
    total = 0

    while True:
        terms = engine.get_random_terms(count=4)
        if len(terms) < 4:
            print("Недостаточно терминов для викторины.")
            break

        target_term = terms[0]
        options = terms[:]
        random.shuffle(options)

        mode = random.choice(["zh_to_en_ru", "en_to_zh", "ru_to_zh"])

        if mode == "zh_to_en_ru":
            print(f"\n{Colors.BOLD}Вопрос {total + 1}:{Colors.END} Что означает термин на китайском: {Colors.YELLOW}{target_term.zh}{Colors.END} ({target_term.pinyin})?")
        elif mode == "en_to_zh":
            print(f"\n{Colors.BOLD}Вопрос {total + 1}:{Colors.END} Как пишется на китайском: {Colors.GREEN}{target_term.en}{Colors.END}?")
        else:
            print(f"\n{Colors.BOLD}Вопрос {total + 1}:{Colors.END} Как переводится на китайский: {Colors.BLUE}{target_term.ru}{Colors.END}?")

        for i, opt in enumerate(options, 1):
            if mode == "zh_to_en_ru":
                print(f"  {i}) {opt.en} / {opt.ru}")
            elif mode == "en_to_zh":
                print(f"  {i}) {opt.zh} ({opt.pinyin}) - {opt.ru}")
            else:
                print(f"  {i}) {opt.zh} ({opt.pinyin}) - {opt.en}")

        try:
            choice = input(f"\n{Colors.BOLD}Ваш ответ (1-4): {Colors.END}").strip()
        except (KeyboardInterrupt, EOFError):
            break

        if choice.lower() in ["q", "exit", "quit"]:
            break

        if not choice.isdigit() or int(choice) not in [1, 2, 3, 4]:
            print(f"{Colors.RED}Пожалуйста, выберите число от 1 до 4.{Colors.END}")
            continue

        selected = options[int(choice) - 1]
        total += 1
        if selected.id == target_term.id:
            score += 1
            print(f"{Colors.GREEN}✓ Правильно! +1 очко (Счет: {score}/{total}){Colors.END}")
        else:
            print(f"{Colors.RED}✗ Неверно. Правильный ответ:{Colors.END} {target_term.en} ↔ {target_term.zh} ({target_term.pinyin}) ↔ {target_term.ru}")

    if total > 0:
        print(f"\n{Colors.BOLD}🏆 Итоговый результат: {score}/{total} ({score/total*100:.1f}%){Colors.END}\n")


async def interactive_repl(engine: TerminologyEngine, translator: TechTranslator):
    """Interactive loop for translating terms."""
    print(f"\n{Colors.BOLD}{Colors.CYAN}══════════════════════════════════════════════════════════════════{Colors.END}")
    print(f"{Colors.BOLD}   🇨🇳 🇬🇧 🇷🇺  Переводчик технических терминов (ZH - EN - RU){Colors.END}")
    print(f"{Colors.BOLD}{Colors.CYAN}══════════════════════════════════════════════════════════════════{Colors.END}")
    print(f"Всего терминов в локальной базе: {Colors.GREEN}{len(engine.terms)}{Colors.END}")
    print(f"{Colors.DIM}Команды:")
    print("  :categories - список категорий")
    print("  :random     - случайный термин")
    print("  :quiz       - режим викторины")
    print("  :help       - помощь")
    print(f"  :exit       - выход{Colors.END}\n")

    while True:
        try:
            user_input = input(f"{Colors.BOLD}Введите термин или фразу > {Colors.END}").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nВыход из программы.")
            break

        if not user_input:
            continue

        if user_input.lower() in [":exit", ":quit", "exit", "quit", "q"]:
            print("До свидания!")
            break
        elif user_input.lower() in [":categories", ":cat"]:
            for cat in engine.get_all_categories():
                print(f"{cat.icon} {cat.id}: {cat.name_ru} / {cat.name_en} / {cat.name_zh}")
            print()
            continue
        elif user_input.lower() in [":random", ":r"]:
            terms = engine.get_random_terms(1)
            if terms:
                print(format_term_card(terms[0]))
            print()
            continue
        elif user_input.lower() in [":quiz", ":q"]:
            await interactive_quiz(engine)
            continue
        elif user_input.lower() in [":help", ":h"]:
            print("Введите любое слово или фразу на английском, русском или китайском (иероглифы или пиньинь).")
            continue

        # Perform translation
        output = await translator.translate(user_input)
        print()
        print(format_translation_output(output))
        print()


def main():
    try:
        asyncio.run(run_cli())
    except KeyboardInterrupt:
        sys.exit(0)


if __name__ == "__main__":
    main()
