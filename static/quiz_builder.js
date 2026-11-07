(() => {
  "use strict";
  const container = document.getElementById("questions");
  const add = document.getElementById("add-question");
  if (!container || !add) return;
  let count = 0;
  function questionCard() {
    if (count >= 30) return;
    count += 1;
    const card = document.createElement("fieldset");
    const legend = document.createElement("legend");
    legend.textContent = "Question " + count;
    card.append(legend);
    const fields = [
      ["question", "Question"],
      ["option_a", "Answer A"], ["option_b", "Answer B"],
      ["option_c", "Answer C"], ["option_d", "Answer D"]
    ];
    for (const [name, title] of fields) {
      const label = document.createElement("label");
      label.textContent = title;
      const input = document.createElement("input");
      input.name = name;
      input.required = true;
      input.maxLength = name === "question" ? 1000 : 500;
      label.append(input);
      card.append(label);
    }
    const label = document.createElement("label");
    label.textContent = "Correct answer";
    const select = document.createElement("select");
    select.name = "correct";
    for (let i = 0; i < 4; i++) {
      const option = document.createElement("option");
      option.value = String(i);
      option.textContent = "ABCD"[i];
      select.append(option);
    }
    label.append(select);
    card.append(label);
    container.append(card);
    add.disabled = count >= 30;
  }
  add.addEventListener("click", questionCard);
  questionCard();
})();
