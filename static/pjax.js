/**
 * PJAX - 无刷新页面加载
 * 拦截内部链接点击，通过 AJAX 加载内容并替换 #pjax-container
 */
(function () {
    'use strict';

    var container = document.getElementById('pjax-container');
    if (!container) return;

    var currentUrl = location.href;
    var loading = false;

    // 进度条
    var bar = document.createElement('div');
    bar.className = 'pjax-bar';
    bar.innerHTML = '<div class="pjax-bar-inner"></div>';
    document.body.appendChild(bar);
    var barInner = bar.querySelector('.pjax-bar-inner');

    function showLoading() {
        bar.classList.add('pjax-bar-active');
        barInner.style.transition = 'none';
        barInner.style.width = '0';
        barInner.offsetHeight; // force reflow
        barInner.style.transition = 'width 0.8s ease';
        barInner.style.width = '70%';
    }

    function hideLoading() {
        barInner.style.width = '100%';
        setTimeout(function () {
            bar.classList.remove('pjax-bar-active');
            barInner.style.width = '0';
        }, 250);
    }

    function getCsrfToken() {
        var meta = document.querySelector('meta[name="csrf-token"]');
        return meta ? meta.getAttribute('content') : '';
    }

    // 显示 flash 横幅
    function showFlashBanner(html) {
        var existing = document.querySelector('.flash-banner-container');
        if (existing) existing.remove();
        var temp = document.createElement('div');
        temp.innerHTML = html;
        var banner = temp.querySelector('.flash-banner-container');
        if (banner) {
            document.body.insertBefore(banner, document.body.firstChild);
            // 自动消失
            var banners = banner.querySelectorAll('.flash-banner');
            banners.forEach(function (b) {
                setTimeout(function () {
                    b.classList.add('hide');
                    setTimeout(function () { if (b.parentElement) b.remove(); }, 300);
                }, 4000);
            });
        }
    }

    function updatePage(html, url) {
        // 更新 CSRF token
        var csrfMatch = html.match(/<meta name="csrf-token" content="([^"]*)"/);
        if (csrfMatch) {
            var meta = document.querySelector('meta[name="csrf-token"]');
            if (meta) meta.setAttribute('content', csrfMatch[1]);
        }

        // 更新标题
        var titleMatch = html.match(/<title>([^<]*)<\/title>/);
        if (titleMatch) {
            document.title = titleMatch[1];
            html = html.replace(/<title>[^<]*<\/title>/, '');
        }

        // 提取 flash 横幅
        var flashMatch = html.match(/<div class="flash-banner-container"[^>]*>[\s\S]*?<\/div>/);
        if (flashMatch) {
            showFlashBanner(flashMatch[0]);
            html = html.replace(flashMatch[0], '');
        }

        // 替换内容
        container.innerHTML = html;

        // 执行内联脚本
        var scripts = container.querySelectorAll('script');
        scripts.forEach(function (oldScript) {
            var newScript = document.createElement('script');
            Array.from(oldScript.attributes).forEach(function (attr) {
                newScript.setAttribute(attr.name, attr.value);
            });
            newScript.textContent = oldScript.textContent;
            oldScript.parentNode.replaceChild(newScript, oldScript);
        });

        // 滚动到顶部
        window.scrollTo({ top: 0, behavior: 'smooth' });

        // 更新 URL
        if (url && url !== currentUrl) {
            history.pushState({ pjax: true, url: url }, '', url);
            currentUrl = url;
        }
    }

    function loadPage(url, addHistory) {
        if (loading) return;
        loading = true;
        showLoading();

        fetch(url, {
            headers: {
                'X-PJAX': 'true',
                'X-Requested-With': 'XMLHttpRequest'
            }
        })
        .then(function (res) {
            if (res.status >= 400) {
                // 错误页面直接跳转
                window.location.href = url;
                return null;
            }
            if (res.redirected && res.url !== url) {
                // 服务端重定向（如登录过期），完整跳转
                window.location.href = res.url;
                return null;
            }
            return res.text();
        })
        .then(function (html) {
            if (html !== null) {
                updatePage(html, addHistory ? url : null);
            }
            hideLoading();
            loading = false;
        })
        .catch(function () {
            window.location.href = url;
        });
    }

    // 拦截链接点击
    document.addEventListener('click', function (e) {
        if (e.button !== 0) return;
        if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;

        var link = e.target.closest('a');
        if (!link) return;

        var href = link.getAttribute('href');
        if (!href || href === '#') return;
        if (href.startsWith('javascript:')) return;
        if (href.startsWith('mailto:')) return;
        if (link.getAttribute('target') === '_blank') return;
        if (link.getAttribute('download') !== null) return;
        if (link.getAttribute('data-no-pjax') !== null) return;
        if (link.closest('form')) return; // 表单内的链接不拦截

        // 只拦截同源链接
        var isExternal = href.startsWith('http://') || href.startsWith('https://');
        if (isExternal && href.indexOf(location.host) === -1) return;

        e.preventDefault();
        loadPage(href, true);
    });

    // 浏览器前进/后退
    window.addEventListener('popstate', function (e) {
        if (e.state && e.state.pjax && e.state.url) {
            loadPage(e.state.url, false);
        }
    });
})();