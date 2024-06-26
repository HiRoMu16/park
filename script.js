document.addEventListener('DOMContentLoaded', function() {
         // �e�[�}�؂�ւ��{�^���̒ǉ�
         const toggleButton = document.createElement('button');
         toggleButton.textContent = 'theme change';
         toggleButton.classList.add('btn', 'btn-outline-secondary', 'theme-toggle');
         document.body.appendChild(toggleButton);
     
         // �e�[�}�؂�ւ��@�\
         toggleButton.addEventListener('click', function() {
             document.body.classList.toggle('dark-mode');
         });
     
         // �N���[�o�[�p�̃R���e�i���쐬
         const cloverContainer = document.createElement('div');
         cloverContainer.id = 'clover-container';
         document.body.appendChild(cloverContainer);
     
         // �N���[�o�[�̃A�j���[�V����
         function createClover() {
                  const clover = document.createElement('div');
                  clover.classList.add('clover');
                  clover.style.left = Math.random() * 100 + 'vw';
                  clover.style.top = Math.random() * 100 + 'vh';
                  cloverContainer.appendChild(clover);
          
                  let angle = Math.random() * Math.PI * 2;
                  let radius = Math.random() * 40 + 10;
                  let speed = Math.random() * 0.02 + 0.005;
                  let centerX = Math.random() * 100;
                  let centerY = Math.random() * 100;
          
                  function animate() {
                      angle += speed;
                      let x = centerX + Math.cos(angle) * radius;
                      let y = centerY + Math.sin(angle) * radius;
                      
                      // �N���[�o�[����ʊO�ɏo�Ȃ��悤�Ɉʒu�𒲐�
                      x = Math.max(0, Math.min(x, 100));
                      y = Math.max(0, Math.min(y, 100));
                      
                      clover.style.transform = `translate(${x}vw, ${y}vh)`;
                      requestAnimationFrame(animate);
                  }
          
                  animate();
         }
     
         // 8���̃N���[�o�[�𐶐�
         for (let i = 0; i < 8; i++) {
             createClover();
         }
     });