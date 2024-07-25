document.addEventListener("DOMContentLoaded", function() {
    let currentIndex = 0;
    const slides = document.querySelectorAll(".slide");
    const totalSlides = slides.length;

    function showSlide(index) {
        const slideshow = document.querySelector(".hero-slideshow");
        slideshow.style.transition = index === totalSlides - 1 ? "none" : "transform 1s ease";
        slideshow.style.transform = `translateX(-${index * 25}%)`;
        //25%�͕\���������X���C�h��4���̂��߁C1/4�����炷�Ӗ�
        currentIndex = index;
    }

    function nextSlide() {
        if (currentIndex === totalSlides -1) {
            showSlide(0);
            setTimeout(() => {
                showSlide(0);// �U�肾���ɖ߂��Ƃ��̃T�C�g
            }, 20);
        } else {
            showSlide(currentIndex + 1);
        }
    }

    setInterval(nextSlide, 5000);//�J�ڎ���

    // Smooth scroll for navigation links
    const navLinks = document.querySelectorAll(".nav-list a");

    navLinks.forEach(link => {
        link.addEventListener("click", function(event) {
            event.preventDefault();
            const targetId = this.getAttribute("href").substring(1);
            const targetSection = document.getElementById(targetId);

            window.scrollTo({
                top: targetSection.offsetTop - 80, // Adjust for fixed header
                behavior: "smooth"
            });
        });
    });

    // Add animation effect to sections on scroll
    const contentSections = document.querySelectorAll(".content-section");

    function revealSection() {
        contentSections.forEach(section => {
            const sectionTop = section.getBoundingClientRect().top;
            const triggerBottom = window.innerHeight - 150;

            if (sectionTop < triggerBottom) {
                section.classList.add("active");
            }
        });
    }

    window.addEventListener("scroll", revealSection);
    revealSection();
});