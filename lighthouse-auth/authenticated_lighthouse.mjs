import fs from "node:fs";
import puppeteer from "puppeteer";
import lighthouse from "lighthouse";

const LOGIN_URL =
    "https://crown-and-conquest-abb2787e2b41.herokuapp.com/accounts/login/";

// ADD OR REMOVE URLS AS NEEDED
const URLS = [
    "https://crown-and-conquest-abb2787e2b41.herokuapp.com/accounts/logout/"
];

const USERNAME = process.env.LIGHTHOUSE_USERNAME;
const PASSWORD = process.env.LIGHTHOUSE_PASSWORD;

if (!USERNAME || !PASSWORD) {
    throw new Error(
        "Set LIGHTHOUSE_USERNAME and LIGHTHOUSE_PASSWORD before running."
    );
}

const browser = await puppeteer.launch({
    headless: true,
    args: ["--remote-debugging-port=9222"],
});

try {
    const page = await browser.newPage();

    await page.goto(LOGIN_URL, {
        waitUntil: "networkidle2",
    });

    await page.type('input[name="login"]', USERNAME);
    await page.type('input[name="password"]', PASSWORD);

    await Promise.all([
        page.waitForNavigation({
            waitUntil: "networkidle2",
        }),
        page.click('button[type="submit"]'),
    ]);

    const endpoint = browser.wsEndpoint();
    const port = Number(new URL(endpoint).port);

    if (!fs.existsSync("reports")) {
        fs.mkdirSync("reports");
    }

    for (const url of URLS) {
        if (!url.trim()) {
            continue;
        }

        console.log(`\n===== TESTING ${url} =====`);

        const filename = url
            .replace(
                "https://crown-and-conquest-abb2787e2b41.herokuapp.com",
                ""
            )
            .replace(/\//g, "_")
            .replace(/^_$/, "home")
            .replace(/^$/, "home");

        // MOBILE REPORT
        const mobile = await lighthouse(url, {
            port,
            output: "html",
            logLevel: "info",
            formFactor: "mobile",
            onlyCategories: [
                "performance",
                "accessibility",
                "best-practices",
                "seo",
            ],
        });

        fs.writeFileSync(
            `reports/mobile-${filename}.html`,
            mobile.report
        );

        // DESKTOP REPORT
        const desktop = await lighthouse(url, {
            port,
            output: "html",
            logLevel: "info",
            formFactor: "desktop",
            screenEmulation: {
                mobile: false,
                width: 1350,
                height: 940,
                deviceScaleFactor: 1,
                disabled: false,
            },
            onlyCategories: [
                "performance",
                "accessibility",
                "best-practices",
                "seo",
            ],
        });

        fs.writeFileSync(
            `reports/desktop-${filename}.html`,
            desktop.report
        );

        console.log("Mobile Scores:");
        console.log({
            performance:
                mobile.lhr.categories.performance.score * 100,
            accessibility:
                mobile.lhr.categories.accessibility.score * 100,
            bestPractices:
                mobile.lhr.categories["best-practices"].score * 100,
            seo:
                mobile.lhr.categories.seo.score * 100,
        });

        console.log("Desktop Scores:");
        console.log({
            performance:
                desktop.lhr.categories.performance.score * 100,
            accessibility:
                desktop.lhr.categories.accessibility.score * 100,
            bestPractices:
                desktop.lhr.categories["best-practices"].score * 100,
            seo:
                desktop.lhr.categories.seo.score * 100,
        });

        console.log(`Created reports for: ${url}`);
    }

    console.log(
        "\n✅ All Lighthouse reports generated successfully."
    );
} finally {
    await browser.close();
}