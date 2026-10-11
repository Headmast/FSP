# Семантическое ревью банка для QA-001

Дата: 2026-10-11. Банк ios-swift-1, 32 задания; разметка Codex. Это не независимая человеческая комиссия и не оценка сложности на аудитории. [Ответы текстами и темы](validation-fixture.json), [заранее заданный протокол](validation-protocol.md).

| Группа ID | Проверяемое утверждение | Основание / граница |
|---|---|---|
| Junior-A/B-1–2 | Optional; value/reference semantics | [Swift Basics](https://docs.swift.org/swift-book/documentation/the-swift-programming-language/thebasics/), [classes/structs](https://docs.swift.org/swift-book/documentation/the-swift-programming-language/classesandstructures/); четыре compiler examples проверены локально |
| Junior-A/B-3–4 | weak, ARC и capture cycle | [ARC](https://github.com/swiftlang/swift-book/blob/main/TSPL.docc/LanguageGuide/AutomaticReferenceCounting.md) |
| Junior-A/B-5–6 | await/cancellation/MainActor | [Concurrency](https://github.com/swiftlang/swift-book/blob/main/TSPL.docc/LanguageGuide/Concurrency.md), [Task](https://developer.apple.com/documentation/swift/task/); речь об UI в iOS |
| Junior-A-7, Junior-B-7 | стабильная identity и локальное State | [Diffable identity](https://developer.apple.com/documentation/UIKit/updating-collection-views-using-diffable-data-sources), [State](https://developer.apple.com/documentation/swiftui/state); темы разные, человеческая эквивалентность не доказана |
| Junior-A/B-8 | JSONDecoder/Decodable и обработка ошибки | [JSONDecoder](https://developer.apple.com/documentation/foundation/jsondecoder); практической задачи в банке нет |
| Middle-A-1–2 | COW и согласованность Hashable | [Array](https://developer.apple.com/documentation/swift/array), [Hashable](https://developer.apple.com/documentation/swift/hashable); утверждения не означают измерение скорости кода |
| Middle-A-3–4 | unowned lifetime; удержание self задачей | [ARC](https://github.com/swiftlang/swift-book/blob/main/TSPL.docc/LanguageGuide/AutomaticReferenceCounting.md), [Task](https://developer.apple.com/documentation/swift/task/); lifetime-анализ — вывод из совместных правил, не обещание автоматического освобождения после cancel |
| Middle-A/B-5–6 | reentrancy и structured tasks | [Concurrency](https://github.com/swiftlang/swift-book/blob/main/TSPL.docc/LanguageGuide/Concurrency.md), [TaskGroup](https://docs.swift.org/latest/documentation/swift/taskgroup/); отмена кооперативна |
| Middle-A-7, Middle-B-8 | freshness/версия запроса | Заранее заданная логическая политика: старый результат не заменяет актуальный. Вопрос не навязывает одну реализацию сети |
| Middle-A-8 | создание и владение ObservableObject | [StateObject](https://developer.apple.com/documentation/swiftui/stateobject), [ObservedObject](https://developer.apple.com/documentation/swiftui/observedobject); корректность зависит от заданной в вопросе роли владельца |
| Middle-B-1–2 | extension dispatch, Sendable | Compiler example; [Concurrency](https://github.com/swiftlang/swift-book/blob/main/TSPL.docc/LanguageGuide/Concurrency.md). Sendable не означает MainActor |
| Middle-B-3–4 | class-bound weak delegate; Memory Graph | ARC и практическая диагностика. Относительная простота этих тем — риск сложности B, фиксируется ниже |
| Middle-B-7 | стабильная diffable identity | [Apple diffable](https://developer.apple.com/documentation/UIKit/updating-collection-views-using-diffable-data-sources). Область проще части вопросов A, нельзя обещать равную сложность для людей |

Семантический oracle использует отдельные тексты ожидаемых ответов и на всех четырёх формах дал 8/8. Программное перемешивание переставляет серверный ключ вместе с вариантом предъявления; этот ключ не участвует в выборе ответов синтетического кандидата или его эталонного уровня.

Обнаруженные границы: варианты имеют разные под-темы, некоторые B-вопросы проще A. На зафиксированной модели знаний правило минимального покрытия каждой области предотвращает ложный Middle сильных Junior. Один Middle-профиль у B повторно не проходит из-за двух пробелов в Swift, тогда как A проходит. Не менять банк или порог по предположению о сложности при отсутствии человеческих данных. Пограничный test–retest нестабилен; выводы и все ошибки сохраняются в [результате](validation-initial.json). Проверять практические задачи, отвлекающие ответы и уровень сложности на QA-002.
