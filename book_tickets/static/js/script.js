document.addEventListener('DOMContentLoaded', function() {
    const bookButtons = document.querySelectorAll('.book-btn');
    bookButtons.forEach(button => {
        button.addEventListener('click', function() {
            const movieId = this.getAttribute('data-movie-id');
            document.querySelector('select[name="movie"]').value = movieId;
        });
    });

    document.querySelector('form').addEventListener('submit', function(event) {
        const tickets = document.querySelector('input[name="tickets"]').value;
        if (tickets === "" || parseInt(tickets) <= 0) {
            event.preventDefault();
            alert('Please select at least one ticket.');
        }
    });
});
