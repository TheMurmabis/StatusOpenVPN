function showPasswordHint(event) {
    event.preventDefault();
    const passwordHint = document.getElementById("passwordHint");
    passwordHint.classList.toggle("show");
}

function showPassword() {
    const passwordInput = document.getElementById("password");
    const toggleIcon = document.getElementById("togglePasswordIcon");
    passwordInput.type = "text";
    toggleIcon.classList.remove("fa-eye");
    toggleIcon.classList.add("fa-eye-slash");
}

function hidePassword() {
    const passwordInput = document.getElementById("password");
    const toggleIcon = document.getElementById("togglePasswordIcon");
    passwordInput.type = "password";
    toggleIcon.classList.remove("fa-eye-slash");
    toggleIcon.classList.add("fa-eye");
}

document.addEventListener("DOMContentLoaded", function () {
    const rememberCheckbox = document.getElementById("remember_me");

    if (rememberCheckbox) {
        if (localStorage.getItem("remember_choice") === "1") {
            rememberCheckbox.checked = true;
        }

        rememberCheckbox.addEventListener("change", function () {
            localStorage.setItem("remember_choice", this.checked ? "1" : "0");
        });
    }
});
