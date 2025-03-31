// AJAX для отметки выполнения задач
document.querySelectorAll('.task-checkbox').forEach(checkbox => {
    checkbox.addEventListener('change', function() {
        const taskId = this.dataset.taskId;
        fetch(`/done/${taskId}`)
            .then(response => {
                if (response.ok) {
                    const label = this.nextElementSibling;
                    const item = this.closest('.list-group-item');
                    
                    if (this.checked) {
                        label.classList.add('text-decoration-line-through');
                        item.classList.add('list-group-item-success');
                    } else {
                        label.classList.remove('text-decoration-line-through');
                        item.classList.remove('list-group-item-success');
                    }
                }
            });
    });
});

// Инициализация datepicker (если подключена соответствующая библиотека)
document.addEventListener('DOMContentLoaded', function() {
    const dateInputs = document.querySelectorAll('input[type="date"]');
    dateInputs.forEach(input => {
        if (!input.value) {
            const today = new Date().toISOString().split('T')[0];
            input.value = today;
        }
    });
});