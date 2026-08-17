const form = document.getElementById('align-form');
const statusEl = document.getElementById('status');
const resultEl = document.getElementById('result');
const outputs = {
    source: document.getElementById('source-output'),
    translation: document.getElementById('target-output'),
    raw: document.getElementById('raw-output'),
};

const otherSide = { source: 'translation', translation: 'source' };

function renderSide(side, words) {
    const container = outputs[side];
    container.innerHTML = '';
    words.forEach((w, i) => {
        const span = document.createElement('span');
        span.className = 'word';
        span.textContent = w.word;
        span.dataset.side = side;
        span.dataset.idx = String(i + 1);
        span.dataset.match = JSON.stringify(w.opposite_translation_index || []);

        const titleParts = [];
        if (w.latin) titleParts.push(w.latin);
        if (w.meaning && w.meaning.length) titleParts.push(w.meaning.join(', '));
        if (w.footnote) titleParts.push(w.footnote);
        if (titleParts.length) span.title = titleParts.join(' — ');

        span.addEventListener('mouseenter', () => highlight(side, span));
        span.addEventListener('mouseleave', clearHighlights);

        container.appendChild(span);
        container.appendChild(document.createTextNode(' '));
    });
}

function highlight(side, span) {
    span.classList.add('self');
    const matchIdxs = JSON.parse(span.dataset.match);
    const otherContainer = outputs[otherSide[side]];
    matchIdxs.forEach((idx) => {
        const match = otherContainer.querySelector(`.word[data-idx="${idx}"]`);
        if (match) match.classList.add('match');
    });
    span.classList.add('match');
}

function clearHighlights() {
    document.querySelectorAll('.word.match, .word.self').forEach((el) => {
        el.classList.remove('match', 'self');
    });
}

form.addEventListener('submit', async (event) => {
    event.preventDefault();
    const formData = new FormData(form);
    const csrfToken = formData.get('csrfmiddlewaretoken');

    statusEl.textContent = 'Aligning…';
    resultEl.hidden = true;

    try {
        const response = await fetch('/api/align/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': csrfToken,
            },
            body: JSON.stringify({
                source_lang: formData.get('source_lang'),
                source: formData.get('source'),
                target_lang: formData.get('target_lang'),
                target: formData.get('target'),
            }),
        });

        const data = await response.json();

        if (!response.ok) {
            statusEl.textContent = data.detail || JSON.stringify(data);
            return;
        }

        renderSide('source', data.source);
        renderSide('translation', data.translation);
        outputs['raw'].innerHTML = data;
        resultEl.hidden = false;
        statusEl.textContent = '';
    } catch (err) {
        statusEl.textContent = `Error: ${err.message}`;
    }
});
