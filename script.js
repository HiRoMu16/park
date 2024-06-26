document.addEventListener('DOMContentLoaded', function() {
         // �e�[�}�؂�ւ��{�^���̒ǉ�
         const toggleButton = document.createElement('button');
         toggleButton.textContent = 'theme Change';
         toggleButton.classList.add('btn', 'btn-outline-secondary', 'theme-toggle');
         document.body.appendChild(toggleButton);
     
         // �e�[�}�؂�ւ��@�\
         toggleButton.addEventListener('click', function() {
             document.body.classList.toggle('dark-mode');
         });
     
         // �N���[�o�[�̃A�j���[�V����
         function createClover() {
             const clover = document.createElement('div');
             clover.classList.add('clover');
             clover.style.left = Math.random() * window.innerWidth + 'px';
             clover.style.top = Math.random() * window.innerHeight + 'px';
             document.body.appendChild(clover);
     
             let angle = 0;
             let radius = Math.random() * 100 + 50;
             let speed = Math.random() * 0.02 + 0.01;
     
             function animate() {
                 angle += speed;
                 let x = Math.cos(angle) * radius;
                 let y = Math.sin(angle) * radius;
                 clover.style.transform = `translate(${x}px, ${y}px)`;
                 requestAnimationFrame(animate);
             }
     
             animate();
         }
     
         // 2-3���̃N���[�o�[�𐶐�
         for (let i = 0; i < Math.floor(Math.random() * 2) + 2; i++) {
             createClover();
         }
     });